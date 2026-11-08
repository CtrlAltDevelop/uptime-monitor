from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import OuterRef, QuerySet, Subquery
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Category, CheckResult, Service

STATUS_LABELS = {"up": "Up", "down": "Down", "unknown": "Unknown"}
STATUS_COLORS = {"up": "success", "down": "danger", "unknown": "info"}

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("name", "services_count", "order")
    list_editable = ("order",)
    search_fields = ("name",)

    @display(description="services")
    def services_count(self, obj: Category) -> int:
        return obj.services.count()


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ("name_header", "category", "type_badge", "status", "interval_seconds", "is_active")
    list_filter = ("category", "check_type", "is_active", "is_public")
    list_filter_submit = True
    search_fields = ("name", "target")
    list_select_related = ("category",)
    warn_unsaved_form = True
    fieldsets = (
        (None, {"fields": ("name", "category", "is_active", "is_public")}),
        ("Health check", {"fields": ("check_type", "target", "port", "expected_status", "keyword", "warn_days")}),
        ("Schedule", {"fields": ("interval_seconds", "timeout_seconds")}),
    )

    def get_queryset(self, request) -> QuerySet[Service]:
        latest = CheckResult.objects.filter(service=OuterRef("pk")).order_by("-checked_at")
        return super().get_queryset(request).annotate(last_up=Subquery(latest.values("is_up")[:1]))

    @display(description="service", ordering="name", header=True)
    def name_header(self, obj: Service) -> list:
        return [obj.name, obj.target, obj.name[:2].upper()]

    @display(description="type", ordering="check_type", label=True)
    def type_badge(self, obj: Service) -> str:
        return obj.get_check_type_display()

    @display(description="status", ordering="last_up", label=STATUS_COLORS)
    def status(self, obj: Service) -> tuple[str, str]:
        key = "unknown" if obj.last_up is None else ("up" if obj.last_up else "down")
        return key, STATUS_LABELS[key]


@admin.register(CheckResult)
class CheckResultAdmin(ModelAdmin):
    list_display = ("service", "checked_at", "result", "latency_ms", "detail")
    list_filter = ("is_up", "service__category", "service")
    list_filter_submit = True
    list_select_related = ("service",)
    list_per_page = 50
    date_hierarchy = "checked_at"

    @display(description="result", ordering="is_up", label=STATUS_COLORS)
    def result(self, obj: CheckResult) -> tuple[str, str]:
        key = "up" if obj.is_up else "down"
        return key, STATUS_LABELS[key]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
