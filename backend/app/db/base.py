# Import all the models, so that Base has them before being imported by Alembic
from app.db.base_class import Base
from app.models.apartment import Apartment, Plan, PlanPriceHistory, ApartmentImage, Neighborhood
from app.models.google_place import GooglePlaceRaw, GoogleApartment
from app.models.user import User, PriceSubscription