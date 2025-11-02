from django.contrib import admin
from django.urls import path
from api import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('create-profile/', views.create_profile, name='create_profile'),
    path('profile', views.list_profiles, name='list_profiles'),
    path('profile/user/<uuid:id>', views.get_profile_by_user, name='get_profile_by_user'),
    path('profile/me', views.get_profile_me, name='get_profile_me'),
    path('profile/<uuid:id>', views.delete_profile, name='delete_profile'),
    path('profile/experience/<uuid:id>', views.delete_experience, name='delete_experience'),
    path('profile/education/<uuid:id>', views.delete_education, name='delete_education'),
    path('profile/experience', views.add_experience, name='add_experience'),
    path('profile/education', views.add_education, name='add_education'),
    path('posts', views.posts, name='posts'),
    path('posts/<uuid:id>', views.post_detail, name='post_detail'),
    path('posts/like/<uuid:id>', views.like_post, name='like_post'),
    path('posts/unlike/<uuid:id>', views.unlike_post, name='unlike_post'),
    path('posts/comment/<uuid:id>', views.add_comment, name='add_comment'),
    path('posts/comment/<uuid:post_id>/<uuid:comment_id>', views.delete_comment, name='delete_comment'),
    path('openai/', views.openai, name='openai'),
]
