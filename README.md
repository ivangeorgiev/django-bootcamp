# Django Bootcamp

[TOC]



## Models

### Get Primary Key field name for Django model

```python
ModelClass._meta.pk.name
instance._meta.pk.name
```



### Get list of field names for Django model

```python
for f in ModelClass._meta.fields:
    print(f.name)
```

```
id False
title False
description False
created_at False
updated_at False
```



```python
# include also foreign models - FK, M2M, etc.
for f in ModelClass._meta.get_fields():
    print(f.name, f.is_relation)
```

```
taskupdate True
id False
title False
description False
created_at False
updated_at False
```

Further Reading:

* https://docs.djangoproject.com/en/stable/ref/models/meta/
* https://docs.djangoproject.com/en/3.2/ref/models/fields/#field-attribute-reference

### Abstract Models

```python
from django.db import models

class IssueBase(models.Model):
	description = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        # Mark model as abstract
        abstract = True
    
class Issue(IssueBase):
    issue_id = models.BigAutoField(primary_key=True)

class IssueUpdate(IssueBase):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE)
```



### Maintain Model History

Decorator is generic through parameters.

```python
# models.py

from functools import wraps
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

```



```python
# models.py
class TaskBaseModel(models.Model):
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.__class__.__name__} {self.id}: {self.title}'

    class Meta:
        abstract = True

class TaskUpdate(TaskBaseModel):
    task = models.ForeignKey('Task', on_delete=models.SET_NULL, null=True )
    # Set auto_now_add from base model to False
    created_at = models.DateTimeField(auto_now_add=False)
    # Set auto_now from base model to False
    updated_at = models.DateTimeField(auto_now=False)
    operation = models.CharField(max_length=32)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(default=MAX_DATETIME)

class Task(TaskBaseModel):
    # Use the @with_history decorator to maintain history records
    @with_history(TaskUpdate, now_field='updated_at', fk_field='task', 
                  operation_field='operation', valid_from_field='valid_from', 
                  valid_until_field='valid_until')
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
```

#### Maintain Deletion

```python
# signals.py
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

```



```python
# apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = 'keephistory'

    def ready(self):
        from . import signals

```



```python
# __init__.py

default_app_config = 'myapp.MyAppConfig'
```



Further reading:

* https://simpleisbetterthancomplex.com/tutorial/2016/07/28/how-to-create-django-signals.html
* https://docs.djangoproject.com/en/3.2/topics/signals/
* https://docs.djangoproject.com/en/3.2/ref/signals/



### Date-Time with Timezone Info

```python
import datetime
from django.utils.timezone import utc

datetime.datetime(3000, 12, 31, 23, 59, 59, 999999, tzinfo=utc)
```



### Get Date Time

```python
from django.utils.dateparse import parse_datetime

MAX_DATETIME = parse_datetime('3000-12-31T23:59:59.999999Z')
```



```python
>>> from django.utils.timezone import now
>>> now()
datetime.datetime(2021, 9, 10, 14, 7, 34, 154380, tzinfo=<UTC>)
```



Further Reading:

* https://docs.djangoproject.com/en/3.2/ref/utils/#django.utils.timezone.now



### Query

#### Retrieve Object

```python
try:
   Task.objects.get(pk=1)
except Task.DoesNotExist:
   print('Not found...')
```





## Customize Admin

Further reading:

* https://docs.djangoproject.com/en/3.2/ref/contrib/admin/

### List Display Fields

```python
# admin.py
from os import read
from django.contrib import admin
from .models import Task, TaskUpdate

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'created_at', 'updated_at')
```



### Read-Only Fields

```python
# admin.py
from os import read
from django.contrib import admin
from .models import Task, TaskUpdate

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at', 'updated_at')
```



### Read-Only ModelAdmin

```python
class ReaOnlyModelAdminMixin:
    def has_add_permission(self, *args, **kwargs):
        return False

    def has_delete_permission(self, *args, **kwargs):
        return False

    def has_change_permission(self, *args, **kwargs) -> bool:
        return False   
```



```python
@admin.register(TaskUpdate)
class TaskUpdateAdmin(ReaOnlyModelAdminMixin, admin.ModelAdmin):
    pass
```

