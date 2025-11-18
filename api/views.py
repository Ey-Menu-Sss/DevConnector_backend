import jwt
import json
import os
from openai import OpenAI
from datetime import datetime, timezone, timedelta
from django.conf import settings
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from .models import User, Profile, Experience, Education, Post, Comment
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = 'HS256'

def create_token(user_id):
    now = datetime.now(timezone.utc)
    payload = {
        'user_id': str(user_id),
        'exp': now + timedelta(days=7),
        'iat': now
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def _get_user_from_token(request):
    token = request.headers.get("x-auth-token")

    if not token:
        return None, Response({"error": "Token missing"}, status=401)
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = decoded.get("user_id")
        user = User.objects.get(id=user_id)
        return user, None
    except jwt.ExpiredSignatureError:
        return None, Response({"error": "Token expired"}, status=401)
    except jwt.InvalidTokenError:
        return None, Response({"error": "Invalid token"}, status=401)
    except User.DoesNotExist:
        return None, Response({"error": "User not found"}, status=404)



@api_view(['POST'])
def register(request):
    name = request.data.get('name')
    email = request.data.get('email')
    password = request.data.get('password')

    if User.objects.filter(email=email).exists():
        return Response({"error": "Email already exists"}, status=status.HTTP_400_BAD_REQUEST)
    
    user = User(name=name, email=email)
    user.set_password(password)
    user.save()

    token = create_token(user.id)

    response = Response({"token": token})
    response.set_cookie(
        key='token',
        value=token,
        httponly=True,
        samesite='None',
        secure=True,
        # secure=False, # for development!
        max_age=7 * 24 * 60 * 60
    )

    return response


@api_view(['POST'])
def login(request):
    email = request.data.get('email')
    password = request.data.get('password')

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "User does not exists!"}, status=status.HTTP_400_BAD_REQUEST)

    if not user.check_password(password):
        return Response({"error": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)

    token = create_token(user.id)

    response = Response({"token": token})
    response.set_cookie(
        key='token',
        value=token,
        httponly=True,
        samesite='None',
        secure=True,
        # secure=False, # for development!
        max_age=7 * 24 * 60 * 60
    )

    return response


@api_view(['POST'])
def create_profile(request):
    user, error = _get_user_from_token(request)
    if error:
        return error

    data = request.data if isinstance(request.data, dict) else json.loads(request.body or '{}')

    # Create or update profile
    profile, _ = Profile.objects.update_or_create(
        user=user,
        defaults={
            "profession": data.get("status", ""),
            "skills": data.get("skills", ""),
            "company": data.get("company", ""),
            "website": data.get("website", ""),
            "location": data.get("location", ""),
            "github_username": data.get("githubusername", ""),
            "bio": data.get("bio", ""),
            "twitter": data.get("twitter", ""),
            "facebook": data.get("facebook", ""),
            "linkedin": data.get("linkedin", ""),
            "instagram": data.get("instagram", ""),
            "youtube": data.get("youtube", ""),
        },
    )

    return Response({"message": "Profile created successfully!", "profile_id": str(profile.id)}, status=201)


@api_view(['GET'])
def list_profiles(request):
    profiles = Profile.objects.select_related('user').all()
    results = []
    for p in profiles:
        results.append({
            "user": {
                "_id": str(p.user.id),
                "name": p.user.name,
                # Placeholder avatar; frontend expects this key
                "avatar": "",
            },
            "status": p.profession,
            "company": p.company or "",
            "location": p.location or "",
            "skills": [s.strip() for s in (p.skills or '').split(',') if s.strip()],
        })
    return Response(results, status=200)


@api_view(['GET'])
def get_profile_by_user(request, id):
    try:
        user = User.objects.get(id=id)
        profile = Profile.objects.get(user=user)
    except (User.DoesNotExist, Profile.DoesNotExist):
        return Response({"error": "Profile not found"}, status=404)

    exp = [{
        "_id": str(e.id),
        "company": e.company,
        "from": e.from_date.strftime('%Y-%m-%d') if e.from_date else "",
        "title": e.title,
        "location": e.location or "",
        "description": e.description or "",
    } for e in profile.experiences.all().order_by('-from_date')]

    edu = [{
        "_id": str(ed.id),
        "school": ed.school,
        "fieldofstudy": ed.field_of_study,
        "description": ed.description or "",
        "degree": ed.degree,
        "from": ed.from_date.strftime('%Y-%m-%d') if ed.from_date else "",
    } for ed in profile.educations.all().order_by('-from_date')]

    data = {
        "user": {
            "_id": str(user.id),
            "name": user.name,
            "avatar": "",
        },
        "status": profile.profession,
        "company": profile.company or "",
        "location": profile.location or "",
        "bio": profile.bio or "",
        "skills": [s.strip() for s in (profile.skills or '').split(',') if s.strip()],
        "social": {
            "facebook": profile.facebook or "",
            "instagram": profile.instagram or "",
            "linkedin": profile.linkedin or "",
            "twitter": profile.twitter or "",
            "youtube": profile.youtube or "",
        },
        "experience": exp,
        "education": edu,
    }
    return Response(data, status=200)


@api_view(['GET'])
def search_profile_by_username(request):
    query = request.GET.get('q', '')
    users = []

    if query:
        users = User.objects.filter(name__icontains=query)

    data = [{"id": i.id, "name": i.name} for i in users]
    return Response(data, status=200)


@api_view(['GET'])
def get_profile_me(request):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return Response(user, status=200)
    # Reuse mapping from get_profile_by_user
    exp = [{
        "_id": str(e.id),
        "company": e.company,
        "from": e.from_date.strftime('%Y-%m-%d') if e.from_date else "",
        "title": e.title,
        "location": e.location or "",
        "description": e.description or "",
    } for e in profile.experiences.all().order_by('-from_date')]
    edu = [{
        "_id": str(ed.id),
        "school": ed.school,
        "fieldofstudy": ed.field_of_study,
        "description": ed.description or "",
        "degree": ed.degree,
        "from": ed.from_date.strftime('%Y-%m-%d') if ed.from_date else "",
    } for ed in profile.educations.all().order_by('-from_date')]
    data = {
        "user": {"_id": str(user.id), "name": user.name, "avatar": ""},
        "status": profile.profession,
        "company": profile.company or "",
        "location": profile.location or "",
        "bio": profile.bio or "",
        "skills": [s.strip() for s in (profile.skills or '').split(',') if s.strip()],
        "social": {
            "facebook": profile.facebook or "",
            "instagram": profile.instagram or "",
            "linkedin": profile.linkedin or "",
            "twitter": profile.twitter or "",
            "youtube": profile.youtube or "",
        },
        "experience": exp,
        "education": edu,
    }
    return Response(data, status=200)


@api_view(['DELETE'])
def delete_profile(request, id):
    try:
        # Get the user by ID from URL
        user = User.objects.get(id=id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        profile = None

    # Delete all user's posts (cascade deletes comments)
    user_posts = Post.objects.filter(user=user)

    # Delete all comments on user's posts manually (safe)
    for post in user_posts:
        Comment.objects.filter(post=post).delete()
    user_posts.delete()

    # Remove user from all post likes (many-to-many)
    for post in Post.objects.all():
        if post.likes.filter(id=user.id).exists():
            post.likes.remove(user)

    # Delete user's profile (cascade deletes experiences, educations, etc.)
    if profile:
        profile.delete()

    # Finally delete the user
    user.delete()

    return Response({"msg": f"Account with id {id} deleted successfully"}, status=200)


@api_view(['DELETE'])
def delete_experience(request, id):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        profile = Profile.objects.get(user=user)
        exp = Experience.objects.get(id=id, profile=profile)
    except (Profile.DoesNotExist, Experience.DoesNotExist):
        return Response({"error": "Experience not found"}, status=404)
    exp.delete()
    experiences = [{
        "_id": str(e.id),
        "company": e.company,
        "from": e.from_date.strftime('%Y-%m-%d') if e.from_date else "",
        "title": e.title,
        "location": e.location or "",
        "description": e.description or "",
    } for e in profile.experiences.all().order_by('-from_date')]
    return Response({"experience": experiences}, status=200)


@api_view(['DELETE'])
def delete_education(request, id):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        profile = Profile.objects.get(user=user)
        edu = Education.objects.get(id=id, profile=profile)
    except (Profile.DoesNotExist, Education.DoesNotExist):
        return Response({"error": "Education not found"}, status=404)
    edu.delete()
    educations = [{
        "_id": str(ed.id),
        "school": ed.school,
        "degree": ed.degree,
        "fieldofstudy": ed.field_of_study,
        "from": ed.from_date.strftime('%Y-%m-%d') if ed.from_date else "",
        "description": ed.description or "",
    } for ed in profile.educations.all().order_by('-from_date')]
    return Response({"education": educations}, status=200)

@api_view(['PUT'])
def add_experience(request):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return Response({"error": "Profile not found"}, status=404)
    data = request.data
    exp = Experience.objects.create(
        profile=profile,
        title=data.get('title', ''),
        company=data.get('company', ''),
        location=data.get('location', ''),
        from_date=data.get('from'),
        description=data.get('description', ''),
    )
    # Return all experiences after adding new one
    experiences = [{
        "_id": str(e.id),
        "company": e.company,
        "from": e.from_date.strftime('%Y-%m-%d') if e.from_date else "",
        "title": e.title,
        "location": e.location or "",
        "description": e.description or "",
    } for e in profile.experiences.all().order_by('-from_date')]
    return Response({"experience": experiences}, status=200)


@api_view(['PUT'])
def add_education(request):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return Response({"error": "Profile not found"}, status=404)
    data = request.data
    edu = Education.objects.create(
        profile=profile,
        school=data.get('school', ''),
        degree=data.get('degree', ''),
        field_of_study=data.get('fieldofstudy', ''),
        from_date=data.get('from'),
        description=data.get('description', ''),
    )
    # Return all educations after adding new one
    educations = [{
        "_id": str(ed.id),
        "school": ed.school,
        "degree": ed.degree,
        "fieldofstudy": ed.field_of_study,
        "from": ed.from_date.strftime('%Y-%m-%d') if ed.from_date else "",
        "description": ed.description or "",
    } for ed in profile.educations.all().order_by('-from_date')]
    return Response({"education": educations}, status=200)


@api_view(['GET', 'POST'])
def posts(request):
    if request.method == 'GET':
        all_posts = Post.objects.all().order_by('-date')
        results = []
        for p in all_posts:
            results.append({
                "_id": str(p.id),
                "user": str(p.user.id),
                "name": p.name,
                "avatar": "",
                "text": p.text,
                "date": p.date.strftime('%Y-%m-%d'),
                "likes": [str(u.id) for u in p.likes.all()],
                "comments": p.comments.count(),
            })
        return Response(results, status=200)

    # POST create
    user, error = _get_user_from_token(request)
    if error:
        return error
    data = request.data
    post = Post.objects.create(user=user, name=user.name, text=data.get('text', ''))
    return Response({
        "_id": str(post.id),
        "user": str(post.user.id),
        "name": post.name,
        "avatar": "",
        "text": post.text,
        "date": post.date.strftime('%Y-%m-%d'),
        "likes": [],
        "comments": 0,
    }, status=201)


@api_view(['GET', 'DELETE'])
def post_detail(request, id):
    try:
        post = Post.objects.get(id=id)
    except Post.DoesNotExist:
        return Response({"error": "Post not found"}, status=404)

    if request.method == 'DELETE':
        user, error = _get_user_from_token(request)
        if error:
            return error
        if post.user != user:
            return Response({"error": "Not authorized"}, status=403)
        post.delete()
        return Response({"msg": "Post deleted"}, status=200)

    # GET
    return Response({
        "_id": str(post.id),
        "user": str(post.user.id),
        "name": post.name,
        "avatar": "",
        "text": post.text,
        "date": post.date.strftime('%Y-%m-%d'),
        "likes": [str(u.id) for u in post.likes.all()],
        "comments": [{
            "_id": str(c.id),
            "user": str(c.user.id),
            "name": c.name,
            "avatar": "",
            "text": c.text,
            "date": c.date.strftime('%Y-%m-%d'),
        } for c in post.comments.all().order_by('-date')],
    }, status=200)


@api_view(['PUT'])
def like_post(request, id):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        post = Post.objects.get(id=id)
    except Post.DoesNotExist:
        return Response({"error": "Post not found"}, status=404)
    post.likes.add(user)
    return Response([str(u.id) for u in post.likes.all()], status=200)


@api_view(['PUT'])
def unlike_post(request, id):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        post = Post.objects.get(id=id)
    except Post.DoesNotExist:
        return Response({"error": "Post not found"}, status=404)
    post.likes.remove(user)
    return Response([str(u.id) for u in post.likes.all()], status=200)


@api_view(['POST'])
def add_comment(request, id):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        post = Post.objects.get(id=id)
    except Post.DoesNotExist:
        return Response({"error": "Post not found"}, status=404)
    data = request.data
    c = Comment.objects.create(post=post, user=user, name=user.name, text=data.get('text', ''))
    return Response({
        "_id": str(c.id),
        "user": str(c.user.id),
        "name": c.name,
        "avatar": "",
        "text": c.text,
        "date": c.date.strftime('%Y-%m-%d'),
    }, status=201)


# delete_post merged into post_detail

@api_view(['DELETE'])
def delete_comment(request, post_id, comment_id):
    user, error = _get_user_from_token(request)
    if error:
        return error
    try:
        post = Post.objects.get(id=post_id)
        comment = Comment.objects.get(id=comment_id, post=post)
    except (Post.DoesNotExist, Comment.DoesNotExist):
        return Response({"error": "Comment not found"}, status=404)
    if comment.user != user:
        return Response({"error": "Not authorized"}, status=403)
    comment.delete()
    # return remaining comments list (optional)
    comments = [{
        "_id": str(c.id),
        "user": str(c.user.id),
        "name": c.name,
        "avatar": "",
        "text": c.text,
        "date": c.date.strftime('%Y-%m-%d'),
    } for c in post.comments.all().order_by('-date')]
    return Response({"msg": "Comment deleted", "comments": comments}, status=200)




@api_view(['POST'])
def openai(request):
    data = json.loads(request.body)
    message = data.get("message")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": message},
        ]
    )

    return Response({"response": response.choices[0].message.content}, status=200)