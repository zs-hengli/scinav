# Generated by Django 5.0.3 on 2024-03-10 06:16

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='myuser',
            name='id',
            field=models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False),
        ),
    ]
