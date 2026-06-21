from django.db import models
class Group(models.Model):
    name = models.CharField(
        max_length=255, unique=True
    )

    def __str__(self):
        return self.name


class Document(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE
    )
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Document - {self.group.name}"


#        groups                        documents
#      id | name                  id | group_id | content     | updated_at
#    --------------               ------------------------------------
#      1  | abc123               1  |    1     | Hello World  | 2026-06-20 21:35:42





