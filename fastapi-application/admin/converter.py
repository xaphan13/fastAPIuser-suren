from typing import Any

from sqladmin.fields import (
    DateTimeField,
)
from sqladmin.forms import (
    ModelConverter as ModelConverterGeneric,
)
from sqladmin.forms import (
    converts,
)
from sqlalchemy.orm import ColumnProperty


class ModelConverter(ModelConverterGeneric):
    @converts("TIMESTAMPAware")
    def conv_timestamp_aware(
        self,
        model: type,
        prop: ColumnProperty,
        kwargs: dict[str, Any],
    ):
        return DateTimeField(**kwargs)
