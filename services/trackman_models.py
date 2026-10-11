"""Private TrackMan archives. These tables do not alter manually entered rounds."""
from extensions import db
from services.time import server_now


class TrackManAccount(db.Model):
    __tablename__ = "trackman_accounts"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    remote_player_id = db.Column(db.String(255))
    credentials = db.Column(db.Text)
    device_credentials = db.Column(db.Text)
    device_expires_at = db.Column(db.DateTime)
    user_code = db.Column(db.String(40))
    verification_uri = db.Column(db.Text)
    poll_interval = db.Column(db.Integer, default=5, nullable=False)
    next_poll_at = db.Column(db.DateTime)
    connected_at = db.Column(db.DateTime)
    last_sync_at = db.Column(db.DateTime)
    sync_state = db.Column(db.String(30), default="disconnected", nullable=False)
    sync_message = db.Column(db.Text)


class TrackManArchive(db.Model):
    __tablename__ = "trackman_archives"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False)
    remote_id = db.Column(db.String(255), nullable=False)
    typename = db.Column(db.String(120))
    payload = db.Column(db.Text, nullable=False)
    fetched_at = db.Column(db.DateTime, nullable=False, default=server_now)
    __table_args__ = (db.UniqueConstraint("user_id", "category", "remote_id"),)


class TrackManSyncRun(db.Model):
    __tablename__ = "trackman_sync_runs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=server_now)
    finished_at = db.Column(db.DateTime)
    state = db.Column(db.String(30), nullable=False, default="running")
    manifest = db.Column(db.Text, nullable=False, default="{}")


class TrackManRound(db.Model):
    __tablename__ = "trackman_rounds"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    remote_id = db.Column(db.String(255), nullable=False)
    environment = db.Column(db.String(20), nullable=False, default="unknown")
    course_name = db.Column(db.String(255), nullable=False)
    started_at = db.Column(db.DateTime)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    holes_to_play = db.Column(db.Integer)
    summary = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "remote_id"),)
