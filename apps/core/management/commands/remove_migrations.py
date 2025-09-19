import os
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Remove all migration files in the Django project."

    def add_arguments(self, parser):
        # Optional argument to specify a custom project root
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="Path to the Django project root (default: settings.BASE_DIR).",  # noqa
        )

    def handle(self, *args, **options):
        # Determine the project root
        from django.conf import settings

        project_root = options["path"] or settings.BASE_DIR

        self.stdout.write(
            self.style.NOTICE(f"Scanning for migration files in: {project_root}\n")
        )

        # Walk through the project directory
        for root, dirs, files in os.walk(project_root):
            if ".venv" in dirs:
                # skips scanning the venv, does NOT delete it
                dirs.remove(".venv")

            if "migrations" in dirs:
                migration_path = os.path.join(root, "migrations")
                self.stdout.write(
                    self.style.WARNING(f"Found 'migrations' folder: {migration_path}")
                )

                # Get all migration files (excluding __init__.py)
                migration_files = [
                    f
                    for f in os.listdir(migration_path)
                    if f.endswith(".py") and f != "__init__.py"
                ]

                if migration_files:
                    for file in migration_files:
                        file_path = os.path.join(migration_path, file)
                        try:
                            os.remove(file_path)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Deleted migration file: {file_path}"
                                )
                            )
                        except Exception as e:
                            self.stderr.write(
                                self.style.ERROR(f"Failed to delete {file_path}: {e}")
                            )
                else:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"No migration files to delete in: {migration_path}"
                        )
                    )

        self.stdout.write(self.style.SUCCESS("\nMigration cleanup complete!"))
