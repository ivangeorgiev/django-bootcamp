from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils.timezone import now
from .models import Task, TaskUpdate

@receiver(pre_delete, sender=Task)
def close_task_updates(sender, instance:Task, **kwargs):
    now_ts = now()
    for update in TaskUpdate.objects.filter(task=instance, valid_until__gt=now_ts):
        update.valid_until = now_ts
        update.save()

# post_save.connect(close_task_updates, sender=Task)
