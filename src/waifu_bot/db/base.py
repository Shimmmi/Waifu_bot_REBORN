"""Base database models and metadata."""
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase

Base: DeclarativeBase = declarative_base()

