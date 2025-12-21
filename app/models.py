from sqlalchemy import Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)

    rooms = relationship(
        "UserRoom",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    users = relationship(
        "UserRoom",
        back_populates="room",
        cascade="all, delete-orphan"
    )

    devices = relationship("Device", back_populates="room")


class UserRoom(Base):
    __tablename__ = "user_rooms"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), primary_key=True)

    role = Column(String, nullable=False, default="viewer")

    user = relationship("User", back_populates="rooms")
    room = relationship("Room", back_populates="users")


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)

    room_id = Column(Integer, ForeignKey("rooms.id"))
    state = Column(JSON, default=dict)

    room = relationship("Room", back_populates="devices")
