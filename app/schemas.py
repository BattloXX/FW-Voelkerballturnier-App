from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from app.models import TournamentStatus, RoundType, MatchStatus, UserRole


class TournamentCreate(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    date: datetime
    status: TournamentStatus = TournamentStatus.registration
    rules_text: Optional[str] = None
    game_duration_prelim: int = 5
    game_duration_inter: int = 10
    game_duration_placement: int = 10
    break_between_games: int = 2
    break_prelim_to_inter: int = 15
    start_time: Optional[datetime] = None
    points_win: int = 2
    points_loss: int = 1
    num_fields: int = 2
    promotions_per_field: int = 6


class TournamentUpdate(TournamentCreate):
    pass


class TournamentOut(BaseModel):
    id: int
    slug: str
    name: str
    description: Optional[str]
    logo_path: Optional[str]
    date: datetime
    status: TournamentStatus
    rules_text: Optional[str]
    game_duration_prelim: int
    game_duration_inter: int
    game_duration_placement: int
    break_between_games: int
    break_prelim_to_inter: int
    start_time: Optional[datetime]
    points_win: int
    points_loss: int
    num_fields: int
    promotions_per_field: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    name: str
    field_group: int
    tournament_id: int


class TeamUpdate(BaseModel):
    name: str


class TeamOut(BaseModel):
    id: int
    tournament_id: int
    name: str
    field_group: int
    pin: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchOut(BaseModel):
    id: int
    tournament_id: int
    round_type: RoundType
    field_number: int
    sequence_number: int
    scheduled_time: Optional[datetime]
    team_a_id: Optional[int]
    team_b_id: Optional[int]
    team_a_placeholder: Optional[str]
    team_b_placeholder: Optional[str]
    score_a: Optional[int]
    score_b: Optional[int]
    players_remaining_a: Optional[int]
    players_remaining_b: Optional[int]
    status: MatchStatus

    model_config = {"from_attributes": True}


class MatchResultInput(BaseModel):
    players_remaining_a: int
    players_remaining_b: int


class MatchScoreInput(BaseModel):
    score_a: int
    score_b: int
    players_remaining_a: Optional[int] = None
    players_remaining_b: Optional[int] = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole
    tournament_id: Optional[int] = None


class UserOut(BaseModel):
    id: int
    username: str
    role: UserRole
    tournament_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str


class LoginForm(BaseModel):
    username: str
    password: str


class StandingEntry(BaseModel):
    rank: int
    team_id: int
    team_name: str
    played: int
    wins: int
    losses: int
    points: int
    diff: int
    promotes: bool


class ScheduleConfig(BaseModel):
    start_time: datetime
    game_duration_prelim: int = 5
    game_duration_inter: int = 10
    game_duration_placement: int = 10
    break_between_games: int = 2
    break_prelim_to_inter: int = 15
