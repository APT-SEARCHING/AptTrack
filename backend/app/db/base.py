# Import all models here so Alembic can discover them for autogenerate.
# These imports look unused but are required — do not remove them.
from app.db.base_class import Base  # noqa: F401
from app.models.apartment import Apartment, ApartmentImage, Neighborhood, Plan, PlanPriceHistory, Unit  # noqa: F401
from app.models.api_cost_log import ApiCostLog  # noqa: F401
from app.models.favorite import ApartmentFavorite  # noqa: F401
from app.models.google_place import GoogleApartment, GooglePlaceRaw  # noqa: F401
from app.models.notification_event import NotificationEvent  # noqa: F401
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.negative_scrape_cache import NegativeScrapeCache  # noqa: F401
from app.models.scrape_run import ScrapeRun  # noqa: F401
from app.models.site_registry import ScrapeSiteRegistry  # noqa: F401
from app.models.user import PriceSubscription, User  # noqa: F401
