"""Base model for all FMP data models."""

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class FMPBaseModel(BaseModel):
    """Base class for all FMP data models.

    Provides common configuration and utility methods for all models.
    """

    model_config = ConfigDict(
        # Allow extra fields from API responses
        extra="ignore",
        # Use enum values in serialization
        use_enum_values=True,
        # Validate on assignment
        validate_assignment=True,
        # Allow arbitrary types
        arbitrary_types_allowed=True,
        # Convert string to datetime
        str_strip_whitespace=True,
        # Populate by name (allow both camelCase and snake_case)
        populate_by_name=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dictionary representation of the model
        """
        return self.model_dump(exclude_none=True, by_alias=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FMPBaseModel":
        """Create model instance from dictionary.

        Args:
            data: Dictionary with model data

        Returns:
            Model instance
        """
        return cls(**data)

    def __repr__(self) -> str:
        """String representation of the model."""
        fields = ", ".join(
            f"{k}={v!r}"
            for k, v in self.model_dump(exclude_none=True).items()
        )
        return f"{self.__class__.__name__}({fields})"
