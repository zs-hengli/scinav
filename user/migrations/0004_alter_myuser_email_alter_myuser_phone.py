# Generated by Django 5.0.3 on 2024-06-05 03:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0003_useroperationlog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='myuser',
            name='email',
            field=models.EmailField(db_default=None, default=None, max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name='myuser',
            name='phone',
            field=models.CharField(db_default=None, default=None, max_length=14, null=True),
        ),
    ]
