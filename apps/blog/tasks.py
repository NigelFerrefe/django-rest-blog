from __future__ import absolute_import, unicode_literals
from celery import shared_task
import redis
from django.conf import settings
import logging
from .models import PostAnalytics, Post

logger = logging.getLogger(__name__)
redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=6379, db=0)

@shared_task
def increment_post_impressions(post_id):
    """
    Increments posts impressions
    """
    
    try: 
        analytics, created = PostAnalytics.objects.get_or_create(post__id=post_id)
        analytics.increment_impression()
    except Exception as e:
        logger.info(f"Error incrementing impressions for post id {post_id}: {str(e)}")
    
    
@shared_task
def sync_impression_to_db():
    """
    Sync impressions from redis to db
    """
    
    keys = redis_client.keys("post:impressions:*")
    for key in keys:
        try:
            post_id = key.decode("utf-8").split(":")[-1]
            impressions = int(redis_client.get(key))
            analytics, _ = PostAnalytics.objects.get_or_create(post__id=post_id)
            analytics.impressions += impressions
            analytics.save()
            analytics._update_click_through_rate()
       
            
            redis_client.delete(key)
        except Exception as e:
            logger.info(f"Error incrementing impressions for key {key}: {str(e)}")
        
        
@shared_task
def increment_post_view_task(slug, ip_address):
    """
    Increment views from a post
    """
    try:
        post = Post.objects.get(slug=slug)
        post_analytics, _ = PostAnalytics.objects.get_or_create(post=post)
        post_analytics.increment_view(ip_address)
    except Exception as e:
        logger.info(f"Error incrementing impressions for Post slug {slug}: {str(e)}")
        
    