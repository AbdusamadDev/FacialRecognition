import django_filters

from api.models import Camera, Criminals, CriminalsRecords


class CameraFilter(django_filters.FilterSet):
    class Meta:
        model = Camera
        fields = ["name", "longitude", "latitude", "id"]


class CriminalsFilter(django_filters.FilterSet):
    class Meta:
        model = Criminals
        fields = ["first_name", "last_name", "age", "date_created"]

class CriminalsRecordFilter(django_filters.FilterSet):
    class Meta:
        model = CriminalsRecords
        fields = '__all__'
