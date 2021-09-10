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
    pk_name = instance._meta.pk.name
    field_names = [f.name for f in instance._meta.fields if f.name != pk_name or include_pk]
    return { fn:getattr(instance, fn) for fn in field_names }

def find_change_type(instance: models.Model):
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

