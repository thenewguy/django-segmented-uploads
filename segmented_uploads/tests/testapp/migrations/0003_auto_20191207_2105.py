# Generated by Django 3.0 on 2019-12-08 03:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('testapp', '0002_auto_20191207_2033'),
    ]

    operations = [
        migrations.AlterField(
            model_name='author',
            name='file',
            field=models.FileField(upload_to=''),
        ),
        migrations.AlterField(
            model_name='author',
            name='photo',
            field=models.FileField(upload_to=''),
        ),
    ]
