from apps.account.models import ListingImage


class ImageCreationService:
    @staticmethod
    def create_images(content_object, images_payload):
        # create images
        image_objs = []

        for img_file in images_payload:
            if hasattr(img_file, "is_primary"):
                is_primary = img_file.is_primary
            else:
                is_primary = False

            img_instance = ListingImage(
                content_object=content_object,
                image=img_file,
                alt_text=img_file.name,
                # TODO: Expect a metadata attached in the payload
                is_primary=is_primary,
            )
            image_objs.append(img_instance)

        images = ListingImage.objects.bulk_create(image_objs)

        print("Images Created", images)
