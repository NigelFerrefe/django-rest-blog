from django.shortcuts import render
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, APIException
import redis
from django.conf import settings
from .models import Post, Heading, PostView, PostAnalytics
from .serializers import PostListSerializer, PostSerializer, HeadingSerializer
from .utils import get_client_ip
from .tasks import increment_post_impressions, increment_post_view_task
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from core.permissions import HasValidAPIKey
from django.core.cache import cache

redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=6379, db=0)


# class PostListView(ListAPIView):
    #queryset = Post.postobjects.all()
    #serializer_class= PostListSerializer

class PostListView(APIView):
    permission_classes = [HasValidAPIKey]
    
    #@method_decorator(cache_page(60*1)) # 1 minute, pero para las analiticas no es tan exacto
    
    def get(self, request, *args, **kwargs):
        try:
            #Manual cache
            cached_posts = cache.get('post_list') # verify if data is in cache 
            if cached_posts:
                for post in cached_posts: # Increment impressions on Redis for cached posts
                    redis_client.incr(f"post:impressions:{post['id']}")
                return Response(cached_posts)
            
            # Get posts from db if not in cache
            posts = Post.postobjects.all()
            if not posts.exists():
                raise NotFound(detail="No posts found")
            
            serialized_posts = PostListSerializer(posts, many=True).data
            # Save data in cache
            cache.set("post_list", serialized_posts, timeout=60 * 1)
            # Increment impressions on Redis
            for post in posts:
                redis_client.incr(f"post:impressions:{post.id}")
                
            
        except Post.DoesNotExist:
            raise NotFound(detail="No posts found")
        except Exception as e:
            raise APIException(detail=f"An unexpected error occurred: {str(e)}")
                
        return Response(serialized_posts)
    
    
#class PostDetailView(RetrieveAPIView):
    #queryset = Post.postobjects.all()
    #serializer_class= PostSerializer
    #lookup_field = 'slug'
    
class PostDetailView(RetrieveAPIView):
    permission_classes = [HasValidAPIKey]

    def get(self, request, slug):
        ip_address = get_client_ip(request)

        try:
            cache_key = f"post_detail:{slug}"
            cached_post = cache.get(cache_key)

            if cached_post:
                increment_post_view_task.delay(cached_post["slug"], ip_address)
                return Response(cached_post)

            post = Post.postobjects.get(slug=slug)

            serialized_post = PostSerializer(post).data

            cache.set(cache_key, serialized_post, timeout=60 * 5)

            increment_post_view_task.delay(post.slug, ip_address)

        except Post.DoesNotExist:
            raise NotFound(detail="The requested post does not exist")

        except Exception as e:
            raise APIException(detail=f"An unexpected error occurred: {str(e)}")

        return Response(serialized_post)
    
    

class PostHeadingView(ListAPIView):
    permission_classes = [HasValidAPIKey]
    serializer_class= HeadingSerializer
    
    def get_queryset(self):
        post_slug = self.kwargs.get("slug")
        return Heading.objects.filter(post__slug = post_slug)
    
    
class IncrementPostClickView(APIView):
    permission_classes = [HasValidAPIKey]
    
    def post(self, request):
        """Increments the click counter relative to his slug"""
        data = request.data

        try:
            post = Post.postobjects.get(slug=data['slug'])
        except Post.DoesNotExist:
            raise NotFound(detail="The requested post does not exist")
        
        try:
            post_analytics, created = PostAnalytics.objects.get_or_create(post=post)
            post_analytics.increment_click()
        except Exception as e:
            raise APIException(detail=f"An error ocurred while updating post analytics: {str(e)}")

        return Response({
            "message": "Click incremented successfully",
            "clicks": post_analytics.clicks
        })