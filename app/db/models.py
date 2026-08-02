from __future__ import annotations
import enum
from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    USER = 'user'
    ADMIN = 'admin'
    SUPER_ADMIN = 'super_admin'


class DealStatus(str, enum.Enum):
    CREATED = 'created'
    WAITING_PAYMENT = 'waiting_payment'
    PAYMENT_VERIFICATION = 'payment_verification'
    AWAITING_TRANSFER = 'awaiting_transfer'
    AWAITING_CONFIRM = 'awaiting_confirm'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'


class PaymentStatus(str, enum.Enum):
    WAITING = 'waiting'
    CONFIRMED = 'confirmed'
    REJECTED = 'rejected'


class WithdrawStatus(str, enum.Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    REJECTED = 'rejected'


class Currency(str, enum.Enum):
    RUB = 'RUB'
    EUR = 'EUR'
    KZT = 'KZT'
    UZS = 'UZS'
    UAH = 'UAH'
    BYN = 'BYN'
    TON = 'TON'
    STARS = 'Stars'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    card_data: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ton_wallet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stars_recipient: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_deals: Mapped[int] = mapped_column(Integer, default=0)
    total_volume: Mapped[float] = mapped_column(Float, default=0.0)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)

    balance_items = relationship('Balance', back_populates='user', cascade='all, delete-orphan')
    sales = relationship('Deal', back_populates='seller', foreign_keys='Deal.seller_id')
    purchases = relationship('Deal', back_populates='buyer', foreign_keys='Deal.buyer_id')
    withdraw_requests = relationship('WithdrawRequest', back_populates='user')


class Deal(Base):
    __tablename__ = 'deals'
    __table_args__ = (UniqueConstraint('deal_number', name='uq_deal_number'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    deal_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    seller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), nullable=False)
    buyer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey('users.id'), nullable=True)
    deal_type: Mapped[str] = mapped_column(String(32), nullable=False, default='gift')
    currency: Mapped[Currency] = mapped_column(Enum(Currency), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DealStatus] = mapped_column(Enum(DealStatus), default=DealStatus.CREATED)
    payment_comment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    seller = relationship('User', foreign_keys=[seller_id], back_populates='sales')
    buyer = relationship('User', foreign_keys=[buyer_id], back_populates='purchases')
    payment = relationship('Payment', back_populates='deal', uselist=False)


class Payment(Base):
    __tablename__ = 'payments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(Integer, ForeignKey('deals.id'), nullable=False)
    buyer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), nullable=False)
    comment: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.WAITING)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    deal = relationship('Deal', back_populates='payment')
    buyer = relationship('User')


class WithdrawRequest(Base):
    __tablename__ = 'withdraw_requests'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[WithdrawStatus] = mapped_column(Enum(WithdrawStatus), default=WithdrawStatus.PENDING)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship('User', back_populates='withdraw_requests')


class Balance(Base):
    __tablename__ = 'balances'
    __table_args__ = (UniqueConstraint('user_id', 'currency', name='uq_user_currency'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)

    user = relationship('User', back_populates='balance_items')


class Setting(Base):
    __tablename__ = 'settings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AdminLog(Base):
    __tablename__ = 'admin_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
