# management/commands/train_recommendations.py
from django.core.management.base import BaseCommand
import pandas as pd
from ai_assistant.ml_recommender import ml_recommender
from ai_assistant.models import UserInteraction, Product, UserProfile

class Command(BaseCommand):
    help = 'Train recommendation models'
    
    def handle(self, *args, **options):
        self.stdout.write('Training recommendation models...')
        
        # Load data
        interactions = UserInteraction.objects.all().values(
            'user_id', 'product_id', 'rating'
        )
        interactions_df = pd.DataFrame(list(interactions))
        
        products = Product.objects.all().values('id', 'name', 'description', 'category', 'tags')
        products_df = pd.DataFrame(list(products))
        
        users = UserProfile.objects.all().values('user_id', 'interests')
        users_df = pd.DataFrame(list(users))
        
        # Train models
        if len(interactions_df) > 10:
            ml_recommender.train_collaborative_filtering(interactions_df)
            ml_recommender.train_content_based_filtering(products_df)
            ml_recommender.train_hybrid_model(interactions_df, products_df, users_df)
            
            self.stdout.write(
                self.style.SUCCESS('Successfully trained recommendation models')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Not enough data to train models')
            )