from django.db import models
from django.utils.timezone import now
from django.utils.dateparse import parse_datetime
from enum import Enum

class OperationType(Enum):
    INSERT = 'I'
    UPDATE = 'U'
    DELETE = 'D'
    SAVE = 'S'

MAX_DATETIME = parse_datetime('3000-12-31T23:59:59.999999Z')

class TaskBaseModel(models.Model):
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.__class__.__name__} {self.id}: {self.title}'

    class Meta:
        abstract = True

def field_values(instance: models.Model, include_pk=True) -> dict:
    pk_name = instance._meta.pk.name
    field_names = [f.name for f in instance._meta.fields if f.name != pk_name or include_pk]
    return { fn:getattr(instance, fn) for fn in field_names }

def find_change_type(instance: models.Model):
    pk_name = instance._meta.pk.name
    pk = getattr(instance, pk_name)
    change_type = OperationType.SAVE
    if pk is None:
        change_type = OperationType.INSERT
    else:
        old_instance = instance.__class__.objects.get(**{pk_name:pk})
        current_values = field_values(old_instance, False)
        new_values = field_values(instance, False)
        if current_values != new_values:
            change_type = OperationType.UPDATE
    return change_type

from functools import wraps

def with_history(history_model, fk_field=None, now_field=None, operation_field=None, valid_from_field=None, valid_until_field=None):
    def decorator(save):
        @wraps(save)
        def wrapper_save(self, *args, **kwargs):
            change_type = find_change_type(self)
            if change_type in [OperationType.INSERT, OperationType.UPDATE]:
                save(self, *args, **kwargs)
                if now_field:
                    now_ts = getattr(self, now_field)
                else:
                    now_ts = now()
                if valid_until_field:
                    for update in history_model.objects.filter(**{fk_field:self, f'{valid_until_field}__gt':now_ts}):
                        setattr(update, valid_until_field, now_ts)
                        update.save()
                values = field_values(self, False)
                if fk_field:
                    values[fk_field] = self
                if operation_field:
                    values[operation_field] = change_type.value
                if valid_from_field:
                    values[valid_from_field] = now_ts
                if valid_until_field:
                    values[valid_until_field] = MAX_DATETIME
                history_model.objects.create(**values)
        return wrapper_save

    return decorator


class TaskUpdate(TaskBaseModel):
    task = models.ForeignKey('Task', on_delete=models.SET_NULL, null=True )
    created_at = models.DateTimeField(auto_now_add=False)
    updated_at = models.DateTimeField(auto_now=False)
    operation = models.CharField(max_length=32)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(default=MAX_DATETIME)


class Task(TaskBaseModel):
    @with_history(TaskUpdate, now_field='updated_at', fk_field='task', 
                  operation_field='operation', valid_from_field='valid_from', 
                  valid_until_field='valid_until')
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
