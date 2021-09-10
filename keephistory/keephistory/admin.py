from os import read
from django.contrib import admin
from .models import Task, TaskUpdate

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')

class ReaOnlyModelAdminMixin:
    def has_add_permission(self, *args, **kwargs):
        return False

    def has_delete_permission(self, *args, **kwargs):
        return False

    def has_change_permission(self, *args, **kwargs) -> bool:
        return False   

    # def get_readonly_fields(self, request, obj=None):
    #     return list(self.readonly_fields) + \
    #            [field.name for field in obj._meta.fields] + \
    #            [field.name for field in obj._meta.many_to_many]

    # def get_actions(self, request):
    #     actions = super().get_actions(request)
    #     del_action = "delete_selected"
    #     if del_action in actions:
    #         del actions[del_action]
    #     return actions

    # def save_model(self, *args, **kwargs):
    #     pass

    # def delete_model(self, *args, **kwargs):
    #     pass

    # def save_related(self, *args, **kwargs):
    #     pass

@admin.register(TaskUpdate)
class TaskUpdateAdmin(ReaOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'task', 'title', 'description', 'operation', 'valid_from', 'valid_until')


