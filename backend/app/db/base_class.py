from sqlalchemy import MetaData
from sqlalchemy.ext.declarative import declarative_base

# Create a metadata instance
metadata = MetaData()

class CustomBase:
    @classmethod
    def __tablename__(cls) -> str:
        """Generate __tablename__ automatically"""
        return cls.__name__.lower()

# Create the declarative base
Base = declarative_base(metadata=metadata, cls=CustomBase)
