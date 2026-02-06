from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

def backfill_hotel_details(apps, schema_editor):
    HotelProfile = apps.get_model('account', 'HotelProfile')
    Address = apps.get_model('core', 'Address')
    
    for hotel in HotelProfile.objects.select_related('company', 'company__address').all():
        # Copy details from company to hotel
        if not hotel.name or hotel.name == "Hotel Name":
            hotel.name = hotel.company.name
            hotel.description = hotel.company.description
            hotel.phone = hotel.company.phone
            hotel.license = hotel.company.license
            
            # Clone address if it exists
            if hotel.company.address:
                # We need a new address instance for the hotel
                # because currently it might be sharing the company address or unrelated
                # But creating a new identical address is safer than linking the same one if usage differs
                old_addr = hotel.company.address
                new_addr = Address.objects.create(
                     country=old_addr.country,
                     state=old_addr.state,
                     city=old_addr.city,
                     street_line1=old_addr.street_line1,
                     postal_code=old_addr.postal_code,
                     latitude=old_addr.latitude,
                     longitude=old_addr.longitude,
                )
                hotel.address = new_addr
            
            hotel.save()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('account', '0005_user_company_user_individual_owner_and_more'),
    ]

    operations = [
        # 1. Add fields (nullable first implicitly, but we set strict defaults in model)
        # Note: In manual migration like this, we usually add fields first.
        migrations.AddField(
            model_name='hotelprofile',
            name='name',
            field=models.CharField(default='Hotel Name', max_length=255, verbose_name='Hotel Name'),
        ),
        migrations.AddField(
            model_name='hotelprofile',
            name='description',
            field=models.TextField(blank=True, verbose_name='Description'),
        ),
        migrations.AddField(
            model_name='hotelprofile',
            name='phone',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Phone Number'),
        ),
        migrations.AddField(
            model_name='hotelprofile',
            name='website',
            field=models.URLField(blank=True, null=True, verbose_name='Website'),
        ),
        migrations.AddField(
            model_name='hotelprofile',
            name='license',
            field=models.FileField(blank=True, null=True, upload_to='hotel/licenses/', verbose_name='Business License'),
        ),
        migrations.AddField(
            model_name='hotelprofile',
            name='address',
            field=models.OneToOneField(
                blank=True, 
                null=True, 
                on_delete=django.db.models.deletion.SET_NULL, 
                related_name='hotel_profile', 
                to='core.address', 
                verbose_name='Address'
            ),
        ),
        
        # 2. Change company to ForeignKey
        migrations.AlterField(
            model_name='hotelprofile',
            name='company',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, 
                related_name='hotels', 
                to='account.companyprofile'
            ),
        ),

        # 3. Data Migration
        migrations.RunPython(backfill_hotel_details),
    ]
