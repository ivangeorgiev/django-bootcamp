import datetime
from functools import wraps
from typing import Callable
import django

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
    """Create dictionary with field values from Django Model object/instance.
    
    Args:
        instance (django.db.models.Model): Instance to extract field values from.
        include_pk (bool): Set to True to include the Primary Key value in the output.
                To exclude the Primary Key, set to False.
    """
    pk_name = instance._meta.pk.name
    field_names = [f.name for f in instance._meta.fields if f.name != pk_name or include_pk]
    return { fn:getattr(instance, fn) for fn in field_names }

def find_change_type(instance: models.Model):
    """Detect if Django model instance is different than currently persisted.
    
    Args:
       instance (django.db.models.Model): Instance to test.

    Returns:
       OperationType: The type of change.
    """
    pk_name = instance._meta.pk.name
    pk = getattr(instance, pk_name)
    if pk is None:
        return OperationType.INSERT

    model = instance.__class__
    try:
        old_instance = model.objects.get(**{pk_name:pk})
    except model.DoesNotExist:
        return OperationType.INSERT

    current_values = field_values(old_instance, False)
    new_values = field_values(instance, False)
    if current_values != new_values:
        return OperationType.UPDATE
    return OperationType.SAVE

def with_history(history_model: django.db.models.Model,
                 now_field:str=None,
                 fk_field:str=None,
                 operation_field:str=None, 
                 valid_from_field:str=None, 
                 valid_until_field:str=None, 
                 max_datetime:datetime=None, 
                 now_func:Callable[[], datetime.datetime]=None):
    """History decorator for Django Model save() method.

    Args:
        history_model (django.db.models.Model): Model to be used to store the history.
        now_field (str): Optional. Field name from the original model to get current timestamp from.
                If not provided, now_func callback is used.
        fk_field (str): Optional. Field name to store the link to the original model.
        operation_field (str): Optional. Field name to store the operation name.
        valid_from_field (str): Optional. Field name to store current timestamp to.
        valid_until_field (str): Optional. Field name to store the max_datetime to.
        max_datetime (datetime.datetime): Optional. Value to be set to valid_until_field.
                If not provided, MAX_DATETIME is used.
        now_func (Callable[[], datetime.datetime]): Optional. Function to use to get current date/time.
                If not provided, use django.utils.timezone.now.
    """
    def decorator(save):
        @wraps(save)
        def wrapper_save(self, *args, **kwargs):
            change_type = find_change_type(self)
            if change_type in [OperationType.INSERT, OperationType.UPDATE]:
                save(self, *args, **kwargs)
                if now_field:
                    now_ts = getattr(self, now_field)
                else:
                    now_ts = now_func() if now_func else now()
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
                    values[valid_until_field] = max_datetime or MAX_DATETIME
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
    
