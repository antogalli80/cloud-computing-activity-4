from tortoise import fields, models


class FileModel(models.Model):
    id = fields.BigIntField(primary_key=True)
    owner = fields.ForeignKeyField(
        "models.UserModel", related_name="files", on_delete=fields.RESTRICT
    )
    filename = fields.CharField(255)
    description = fields.CharField(1000, null=True)
    content_key = fields.CharField(64, null=True)
    content_type = fields.CharField(255, null=True)
    size_bytes = fields.BigIntField(default=0)
    sha256 = fields.CharField(64, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "files"
        indexes = (("owner_id", "id"),)
