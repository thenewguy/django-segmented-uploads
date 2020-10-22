from django.db import models
from django.urls import reverse


class Author(models.Model):
    name = models.CharField(max_length=200)
    file = models.FileField()
    photo = models.FileField()

    def get_absolute_url(self):
        return reverse('author-update', kwargs={'pk': self.pk})
