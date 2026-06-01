# Generated manually for clean guesthouse structure
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listing', '0012_alter_eventspacelisting_hotel'),
        ('account', '0004_alter_companyprofile_address_and_more'),
        ('core', '0003_alter_address_country'),
    ]

    operations = [
        # GuestHouseProfile already maps to the guest_houses table in the older
        # migration history. Keep the state transition, but do not recreate the table.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='GuestHouseProfile',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='Id')),
                        ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                        ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated_at')),
                        ('title', models.CharField(max_length=255, verbose_name='Title')),
                        ('description', models.TextField(blank=True, verbose_name='Description')),
                        ('base_price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Price')),
                        ('currency', models.CharField(default='ETB', max_length=3, verbose_name='Currency')),
                        ('is_active', models.BooleanField(default=True, verbose_name='Is Active')),
                        ('rating', models.DecimalField(blank=True, decimal_places=2, max_digits=3, null=True, verbose_name='Average Rating')),
                        ('address', models.OneToOneField(on_delete=django.db.models.deletion.RESTRICT, related_name='guesthouse_profile', to='core.address', verbose_name='Address')),
                        ('amenities', models.ManyToManyField(blank=True, related_name='guest_house_profiles', to='listing.amenity', verbose_name='Property Amenities')),
                        ('company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='guest_house_profiles', to='account.companyprofile', verbose_name='Company')),
                        ('facility', models.ManyToManyField(blank=True, related_name='guest_house_profiles', to='core.facility', verbose_name='Facility')),
                        ('individual_owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='guest_house_profiles', to='account.individualownerprofile', verbose_name='Individual Owner')),
                    ],
                    options={
                        'verbose_name': 'Guest House Profile',
                        'verbose_name_plural': 'Guest House Profiles',
                        'db_table': 'guest_houses',
                    },
                ),
            ],
            database_operations=[],
        ),
        
        # Create GuestHouseRoom
        migrations.CreateModel(
            name='GuestHouseRoom',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='Id')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated_at')),
                ('title', models.CharField(max_length=255, verbose_name='Title')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('base_price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Price')),
                ('currency', models.CharField(default='ETB', max_length=3, verbose_name='Currency')),
                ('is_active', models.BooleanField(default=True, verbose_name='Is Active')),
                ('number_of_guests', models.PositiveIntegerField(default=1)),
                ('total_units', models.PositiveIntegerField(default=1, verbose_name='Total Rooms of This Type')),
                ('bed_type', models.CharField(choices=[('king', 'King'), ('queen', 'Queen'), ('twin', 'Twin'), ('double', 'Double'), ('mixed', 'Mixed/Multiple')], default='mixed', max_length=20)),
                ('room_size_sqm', models.PositiveIntegerField(blank=True, null=True)),
                ('amenities', models.ManyToManyField(blank=True, related_name='guest_house_rooms', to='listing.amenity', verbose_name='Room Amenities')),
                ('guest_house', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='listing.guesthouseprofile', verbose_name='Guest House')),
            ],
            options={
                'verbose_name': 'Guest House Room',
                'verbose_name_plural': 'Guest House Rooms',
                'db_table': 'guest_house_rooms',
            },
        ),
        
        # Create GuestHouseInventory
        migrations.CreateModel(
            name='GuestHouseInventory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='Id')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated_at')),
                ('date', models.DateField(db_index=True)),
                ('available_rooms', models.PositiveIntegerField()),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('guest_house_room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inventories', to='listing.guesthouseroom')),
            ],
            options={
                'db_table': 'guest_house_inventories',
                'ordering': ['date'],
                'unique_together': {('guest_house_room', 'date')},
            },
        ),
        
        # Update GuestHouseBookingItem
        migrations.AlterField(
            model_name='guesthousebookingitem',
            name='room',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='booking_items', to='listing.guesthouseroom', verbose_name='Room'),
        ),
        
        # Add constraints in state only; the physical table already has this constraint.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(
                    model_name='guesthouseprofile',
                    constraint=models.CheckConstraint(
                        condition=models.Q(
                            models.Q(('individual_owner__isnull', False), ('company__isnull', True)),
                            models.Q(('individual_owner__isnull', True), ('company__isnull', False)),
                            _connector='OR',
                        ),
                        name='guest_house_owner_must_exist',
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
