from pydantic import BaseModel


class PersonalizedMessage(BaseModel):
    subject: str
    body: str


class Sender(BaseModel):
    name: str
    email: str


class Mail(BaseModel):
    sender: Sender
    to: str
    subject: str
    body: str