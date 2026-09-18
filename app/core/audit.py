from tortoise import fields, models


class AuditEvent(models.Model):
    id = fields.BigIntField(primary_key=True)
    occurred_at = fields.DatetimeField(auto_now_add=True, db_index=True)
    service = fields.CharField(32)
    event = fields.CharField(64)
    request_id = fields.UUIDField(db_index=True)
    actor_id = fields.BigIntField(null=True, db_index=True)
    resource_id = fields.BigIntField(null=True)
    outcome = fields.CharField(32)

    class Meta:
        table = "audit_events"


class DatabaseAudit:
    def __init__(self, service):
        self.service = service

    async def record(self, event, context, *, actor_id=None, resource_id=None, outcome="success"):
        await AuditEvent.create(
            service=self.service,
            event=event,
            request_id=context.request_id,
            actor_id=actor_id,
            resource_id=resource_id,
            outcome=outcome,
        )
