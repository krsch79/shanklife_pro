# Generated: 2026-04-18 01:35 Europe/Oslo
# Version: 1.0.0

from extensions import db


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    gender = db.Column(db.String(10), nullable=False, default="male")
    default_hcp = db.Column(db.Float, nullable=False)
    profile_image_filename = db.Column(db.String(255), nullable=True)
    legacy_source = db.Column(db.String(50), nullable=True)
    legacy_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    round_players = db.relationship("RoundPlayer", back_populates="player")
    user_accounts = db.relationship("User", back_populates="player")
    series_memberships = db.relationship("SeriesPlayer", back_populates="player")
    hole_default_clubs = db.relationship("PlayerHoleDefaultClub", back_populates="player")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    player = db.relationship("Player", back_populates="user_accounts")
    stats_rounds = db.relationship("Round", back_populates="stats_user")
    ai_fix_requests = db.relationship("AiFixRequest", back_populates="created_by_user")


class AiFixRequest(db.Model):
    __tablename__ = "ai_fix_requests"

    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="new")
    admin_note = db.Column(db.Text, nullable=True)
    github_issue_number = db.Column(db.Integer, nullable=True)
    github_issue_url = db.Column(db.String(255), nullable=True)
    github_sync_error = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), onupdate=db.func.now())

    created_by_user = db.relationship("User", back_populates="ai_fix_requests")


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    hole_count = db.Column(db.Integer, nullable=False, default=18)
    legacy_source = db.Column(db.String(50), nullable=True)
    legacy_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    holes = db.relationship(
        "CourseHole",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseHole.hole_number",
    )

    tees = db.relationship(
        "CourseTee",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseTee.display_order",
    )

    rounds = db.relationship("Round", back_populates="course")
    series = db.relationship("Series", back_populates="course")


class CourseHole(db.Model):
    __tablename__ = "course_holes"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    hole_number = db.Column(db.Integer, nullable=False)
    par = db.Column(db.Integer, nullable=False)
    stroke_index = db.Column(db.Integer, nullable=False)

    course = db.relationship("Course", back_populates="holes")
    tee_lengths = db.relationship(
        "CourseTeeLength",
        back_populates="hole",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("course_id", "hole_number", name="uq_course_hole_number"),
    )


class CourseTee(db.Model):
    __tablename__ = "course_tees"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    course = db.relationship("Course", back_populates="tees")
    lengths = db.relationship(
        "CourseTeeLength",
        back_populates="tee",
        cascade="all, delete-orphan",
        order_by="CourseTeeLength.hole_number",
    )
    ratings = db.relationship(
        "CourseTeeRating",
        back_populates="tee",
        cascade="all, delete-orphan",
        order_by="CourseTeeRating.gender",
    )
    round_players = db.relationship("RoundPlayer", back_populates="selected_tee")

    __table_args__ = (
        db.UniqueConstraint("course_id", "name", name="uq_course_tee_name"),
        db.UniqueConstraint("course_id", "display_order", name="uq_course_tee_display_order"),
    )


class CourseTeeLength(db.Model):
    __tablename__ = "course_tee_lengths"

    id = db.Column(db.Integer, primary_key=True)
    tee_id = db.Column(db.Integer, db.ForeignKey("course_tees.id"), nullable=False)
    hole_id = db.Column(db.Integer, db.ForeignKey("course_holes.id"), nullable=False)
    hole_number = db.Column(db.Integer, nullable=False)
    length_meters = db.Column(db.Integer, nullable=False)

    tee = db.relationship("CourseTee", back_populates="lengths")
    hole = db.relationship("CourseHole", back_populates="tee_lengths")

    __table_args__ = (
        db.UniqueConstraint("tee_id", "hole_number", name="uq_tee_hole_number"),
        db.UniqueConstraint("tee_id", "hole_id", name="uq_tee_hole_id"),
    )


class CourseTeeRating(db.Model):
    __tablename__ = "course_tee_ratings"

    id = db.Column(db.Integer, primary_key=True)
    tee_id = db.Column(db.Integer, db.ForeignKey("course_tees.id"), nullable=False)
    gender = db.Column(db.String(10), nullable=False)  # male / female
    slope = db.Column(db.Integer, nullable=False)
    course_rating = db.Column(db.Float, nullable=False)

    tee = db.relationship("CourseTee", back_populates="ratings")

    __table_args__ = (
        db.UniqueConstraint("tee_id", "gender", name="uq_tee_gender_rating"),
    )


class Round(db.Model):
    __tablename__ = "rounds"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="ongoing")
    started_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    finished_at = db.Column(db.DateTime, nullable=True)
    stats_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    weather_json = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    legacy_source = db.Column(db.String(50), nullable=True)
    legacy_id = db.Column(db.Integer, nullable=True)

    course = db.relationship("Course", back_populates="rounds")
    stats_user = db.relationship("User", back_populates="stats_rounds")
    round_players = db.relationship(
        "RoundPlayer",
        back_populates="round",
        cascade="all, delete-orphan",
        order_by="RoundPlayer.id",
    )
    score_entries = db.relationship(
        "ScoreEntry",
        back_populates="round",
        cascade="all, delete-orphan",
    )
    images = db.relationship(
        "RoundImage",
        back_populates="round",
        cascade="all, delete-orphan",
        order_by="RoundImage.uploaded_at",
    )


class RoundPlayer(db.Model):
    __tablename__ = "round_players"

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    selected_tee_id = db.Column(db.Integer, db.ForeignKey("course_tees.id"), nullable=True)
    player_name_snapshot = db.Column(db.String(120), nullable=False)
    hcp_for_round = db.Column(db.Float, nullable=False)

    round = db.relationship("Round", back_populates="round_players")
    player = db.relationship("Player", back_populates="round_players")
    selected_tee = db.relationship("CourseTee", back_populates="round_players")
    score_entries = db.relationship(
        "ScoreEntry",
        back_populates="round_player",
        cascade="all, delete-orphan",
        order_by="ScoreEntry.hole_number",
    )


class ScoreEntry(db.Model):
    __tablename__ = "score_entries"

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    round_player_id = db.Column(db.Integer, db.ForeignKey("round_players.id"), nullable=False)
    hole_number = db.Column(db.Integer, nullable=False)
    strokes = db.Column(db.Integer, nullable=True)
    tee_club_id = db.Column(db.Integer, db.ForeignKey("clubs.id"), nullable=True)

    round = db.relationship("Round", back_populates="score_entries")
    round_player = db.relationship("RoundPlayer", back_populates="score_entries")
    tee_club = db.relationship("Club", back_populates="score_entries")
    detailed_stat = db.relationship(
        "ScoreStat",
        back_populates="score_entry",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "round_player_id",
            "hole_number",
            name="uq_round_player_hole",
        ),
    )


class ScoreStat(db.Model):
    __tablename__ = "score_stats"

    id = db.Column(db.Integer, primary_key=True)
    score_entry_id = db.Column(db.Integer, db.ForeignKey("score_entries.id"), nullable=False, unique=True)
    drive_distance_m = db.Column(db.Integer, nullable=True)
    fairway_result = db.Column(db.String(50), nullable=True)  # fairway or green result
    putts = db.Column(db.Integer, nullable=True)
    last_putt_distance_m = db.Column(db.Float, nullable=True)

    score_entry = db.relationship("ScoreEntry", back_populates="detailed_stat")


class Club(db.Model):
    __tablename__ = "clubs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    legacy_source = db.Column(db.String(50), nullable=True)
    legacy_id = db.Column(db.Integer, nullable=True)

    score_entries = db.relationship("ScoreEntry", back_populates="tee_club")
    player_hole_defaults = db.relationship("PlayerHoleDefaultClub", back_populates="club")


class PlayerHoleDefaultClub(db.Model):
    __tablename__ = "player_hole_default_clubs"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    hole_number = db.Column(db.Integer, nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.id"), nullable=False)

    player = db.relationship("Player", back_populates="hole_default_clubs")
    course = db.relationship("Course")
    club = db.relationship("Club", back_populates="player_hole_defaults")

    __table_args__ = (
        db.UniqueConstraint(
            "player_id",
            "course_id",
            "hole_number",
            name="uq_player_course_hole_default_club",
        ),
    )


class Series(db.Model):
    __tablename__ = "series"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    min_qualifying_rounds = db.Column(db.Integer, nullable=False, default=20)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    course = db.relationship("Course", back_populates="series")
    players = db.relationship(
        "SeriesPlayer",
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="SeriesPlayer.display_order",
    )


class SeriesPlayer(db.Model):
    __tablename__ = "series_players"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    series = db.relationship("Series", back_populates="players")
    player = db.relationship("Player", back_populates="series_memberships")

    __table_args__ = (
        db.UniqueConstraint("series_id", "player_id", name="uq_series_player"),
    )


class RoundImage(db.Model):
    __tablename__ = "round_images"

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    hole_number = db.Column(db.Integer, nullable=True)
    tagged_player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    legacy_source = db.Column(db.String(50), nullable=True)
    legacy_id = db.Column(db.Integer, nullable=True)

    round = db.relationship("Round", back_populates="images")
    tagged_player = db.relationship("Player")
