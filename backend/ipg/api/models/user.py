import pycountry
import pydantic
from pydantic import EmailStr
from sqlmodel import AutoString, Field

from ipg.api.models.shared import DBModel


class UserBase(DBModel):
    username: str = Field(default=None, index=True, min_length=3)
    email_address: EmailStr = Field(unique=True, index=True, sa_type=AutoString)
    country: str | None = None

    @pydantic.field_validator("country")
    @classmethod
    def country_code(cls, v: str):
        """
        It checks that the country code is a valid 3-letter country code
        :param v: The value to be validated
        :return: The country code
        """
        if v and pycountry.countries.get(alpha_3=v.upper()) is None:
            raise ValueError("Country must be a valid 3-letter country code")
        return v


class UserCreate(UserBase):
    password: str


class UserUpdate(UserBase):
    pass


class UserUpdatePassword(DBModel):
    password: str
