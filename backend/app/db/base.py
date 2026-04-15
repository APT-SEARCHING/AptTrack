# Import all models here so Alembic can discover them for autogenerate.
# These imports look unused but are required — do not remove them.
from app.db.base_class import Base  # noqa: F401
from app.models.apartment import Apartment, ApartmentImage, Neighborhood, Plan, PlanPriceHistory  # noqa: F401
from app.models.google_place import GoogleApartment, GooglePlaceRaw  # noqa: F401
from app.models.user import PriceSubscription, User  # noqa: F401
from app.models.site_registry import ScrapeSiteRegistry  # noqa: F401
