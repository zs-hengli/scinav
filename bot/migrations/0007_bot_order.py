# Generated by Django 5.0.3 on 2024-07-02 06:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bot', '0006_alter_bot_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='bot',
            name='order',
            field=models.IntegerField(db_default=0, default=0),
        ),
    ]