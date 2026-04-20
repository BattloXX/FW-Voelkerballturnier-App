from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Float, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class TournamentStatus(str, enum.Enum):
    registration = "registration"
    active = "active"
    finished = "finished"


class RoundType(str, enum.Enum):
    prelim = "prelim"
    inter = "inter"
    placement = "placement"


class MatchStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    finished = "finished"


class UserRole(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    referee = "referee"


class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    logo_path = Column(String(500))
    date = Column(DateTime, nullable=False)
    status = Column(Enum(TournamentStatus), default=TournamentStatus.registration)
    rules_text = Column(Text)
    game_duration_prelim = Column(Integer, default=5)
    game_duration_inter = Column(Integer, default=10)
    game_duration_placement = Column(Integer, default=10)
    break_between_games = Column(Integer, default=2)
    break_prelim_to_inter = Column(Integer, default=15)
    start_time = Column(DateTime)
    inter_start_time = Column(DateTime, nullable=True)
    placement_start_time = Column(DateTime, nullable=True)
    points_win = Column(Integer, default=2)
    points_loss = Column(Integer, default=1)
    num_fields = Column(Integer, default=2)
    promotions_per_field = Column(Integer, default=6)
    created_at = Column(DateTime, server_default=func.now())

    teams = relationship("Team", back_populates="tournament", cascade="all, delete-orphan")
    matches = relationship("Match", back_populates="tournament", cascade="all, delete-orphan")
    users = relationship("User", back_populates="tournament")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    name = Column(String(200), nullable=False)
    field_group = Column(Integer, nullable=False)
    pin = Column(String(10), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    tournament = relationship("Tournament", back_populates="teams")
    matches_as_a = relationship("Match", foreign_keys="Match.team_a_id", back_populates="team_a")
    matches_as_b = relationship("Match", foreign_keys="Match.team_b_id", back_populates="team_b")
    players = relationship("Player", back_populates="team", cascade="all, delete-orphan", order_by="Player.jersey_number")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    name = Column(String(100), nullable=False)
    jersey_number = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    team = relationship("Team", back_populates="players")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    round_type = Column(Enum(RoundType), nullable=False)
    field_number = Column(Integer, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    scheduled_time = Column(DateTime)
    team_a_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team_b_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team_a_placeholder = Column(String(100))
    team_b_placeholder = Column(String(100))
    score_a = Column(Integer)
    score_b = Column(Integer)
    players_remaining_a = Column(Integer)
    players_remaining_b = Column(Integer)
    status = Column(Enum(MatchStatus), default=MatchStatus.pending)
    entered_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    entered_at = Column(DateTime)

    tournament = relationship("Tournament", back_populates="matches")
    team_a = relationship("Team", foreign_keys=[team_a_id], back_populates="matches_as_a")
    team_b = relationship("Team", foreign_keys=[team_b_id], back_populates="matches_as_b")
    entered_by_user = relationship("User", foreign_keys=[entered_by])


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    tournament = relationship("Tournament", back_populates="users")
