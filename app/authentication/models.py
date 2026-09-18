from tortoise import fields, models


class UserModel(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(254, unique=True)
    password_hash = fields.CharField(512)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "users"


class SessionModel(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.OneToOneField(
        "models.UserModel", related_name="session", on_delete=fields.CASCADE
    )
    digest = fields.CharField(64, unique=True)
    created_at = fields.DatetimeField()
    last_seen_at = fields.DatetimeField()
    expires_at = fields.DatetimeField(db_index=True)

    class Meta:
        table = "sessions"
