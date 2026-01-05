from django.db import migrations, models
import django.db.models.deletion

def ensure_null_column(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            # Check if column exists first
            cursor.execute("""
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='microfinance_penalty' AND column_name='Installment_id'
            """)
            if cursor.fetchone():
                cursor.execute('ALTER TABLE microfinance_penalty ALTER COLUMN "Installment_id" DROP NOT NULL')
            else:
                # If it doesn't exist, we'll let AddField in database_operations handle it
                # But we only want to ADD it if it doesn't exist.
                # Since AddField is not conditional, we might need RunSQL for conditional add.
                pass

class Migration(migrations.Migration):

    dependencies = [
        ("microfinance", "0007_penalty_installment_waiver"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # If column exists, drop NOT NULL. If not, AddField will be needed.
                # To be safe, let's just use raw SQL to add if missing, then drop not null.
                migrations.RunSQL(
                    sql="""
                        DO $$ 
                        BEGIN 
                            IF EXISTS (SELECT 1 FROM information_schema.columns 
                                       WHERE table_name='microfinance_penalty' AND column_name='Installment_id') THEN
                                ALTER TABLE microfinance_penalty ALTER COLUMN "Installment_id" DROP NOT NULL;
                            ELSE
                                ALTER TABLE microfinance_penalty ADD COLUMN "Installment_id" integer REFERENCES microfinance_installments(id) ON DELETE CASCADE;
                                ALTER TABLE microfinance_penalty ALTER COLUMN "Installment_id" DROP NOT NULL;
                            END IF;
                        END $$;
                    """,
                    reverse_sql="ALTER TABLE microfinance_penalty DROP COLUMN IF EXISTS \"Installment_id\";"
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="penalty",
                    name="Installment",
                    field=models.ForeignKey(
                        null=True,
                        blank=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="microfinance.installments",
                    ),
                ),
            ],
        ),
    ]
