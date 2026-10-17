# Deploy to Google Cloud (Cloud Run + Cloud SQL), step by step

Everything is typed in **Cloud Shell**, the terminal built into the Google Cloud console, so you install nothing
on your laptop. About 45 minutes the first time, most of it waiting for builds.

What you end up with: Postgres 16 on **Cloud SQL**, the API on **Cloud Run** (one always-on instance, because the
job worker and scheduler run inside it), the web app on **Cloud Run**, and the fictional "Lumora Bank" demo data
loaded by a one-off **Cloud Run job**.

> Cost: Cloud SQL and an always-on Cloud Run instance bill while they exist. Expect a few dollars a day; check the
> Google Cloud pricing pages for your region. Use the teardown at the bottom when you are done.

## 0. Before you start

- A Google account with **billing enabled** and a project (note its **Project ID**, not the name).
- On your laptop, in the repository folder, make the upload zip:

      powershell -ExecutionPolicy Bypass -File deploy\gcp\make-zip.ps1

  That creates `guru-gcp.zip` (about 3 MB: no `node_modules`, no build output).

## 1. Open Cloud Shell and set variables

In the console click the **>_** icon (top right). Then:

    gcloud config set project YOUR_PROJECT_ID
    export PROJECT_ID=$(gcloud config get-value project)
    export REGION=asia-southeast1
    gcloud services enable run.googleapis.com sqladmin.googleapis.com cloudbuild.googleapis.com \
      artifactregistry.googleapis.com secretmanager.googleapis.com

(Cloud Shell forgets variables if it restarts: re-run the `export` lines when that happens.)

## 2. Upload the code

Cloud Shell menu **⋮ → Upload** → choose `guru-gcp.zip`. Then:

    mkdir -p ~/guru && cd ~/guru && unzip -q ~/guru-gcp.zip && ls

You should see `apps  deploy  docs  packages ...`. Every command below runs from `~/guru`.

## 3. A place to keep the images

    gcloud artifacts repositories create guru --repository-format=docker --location=$REGION
    export REPO=$REGION-docker.pkg.dev/$PROJECT_ID/guru

## 4. The database (takes 5 to 10 minutes)

    export DB_PASS=$(openssl rand -hex 16)
    gcloud sql instances create guru-db --database-version=POSTGRES_16 --edition=ENTERPRISE \
      --tier=db-f1-micro --region=$REGION --root-password=$(openssl rand -hex 16)
    gcloud sql databases create guru --instance=guru-db
    gcloud sql users create guru --instance=guru-db --password=$DB_PASS
    echo "DB password: $DB_PASS"        # copy this somewhere safe

The `guru` user owns the tables. That matters: the app's two other database roles are created by the first
migration, and the table owner is exempt from row-level security, so the operator connection uses the owner.

## 5. Secrets

    export CONN=$PROJECT_ID:$REGION:guru-db
    printf 'postgresql+psycopg://guru:%s@/guru?host=/cloudsql/%s' "$DB_PASS" "$CONN" | gcloud secrets create guru-database-url --data-file=-
    openssl rand -hex 32 | tr -d '\n' | gcloud secrets create guru-secret-key --data-file=-
    printf '%s' 'CHOOSE-AN-ADMIN-PASSWORD'  | gcloud secrets create guru-admin-password  --data-file=-
    printf '%s' 'CHOOSE-A-VIEWER-PASSWORD'  | gcloud secrets create guru-viewer-password --data-file=-
    printf '%s' 'CHOOSE-A-DEMO-PASSWORD'    | gcloud secrets create guru-demo-password   --data-file=-

Pick real passwords in the three `CHOOSE-...` lines. `admin` / `bank` are the stock logins; the demo logins
(`demo.admin`, `farah.supervisor`, ...) use the demo password.

Let the services read them and reach the database:

    PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
    SA=$PROJECT_NUMBER-compute@developer.gserviceaccount.com
    for ROLE in roles/secretmanager.secretAccessor roles/cloudsql.client roles/artifactregistry.writer \
                roles/cloudbuild.builds.builder roles/logging.logWriter roles/storage.objectViewer; do
      gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=$ROLE --quiet >/dev/null
    done

## 6. Build and start the API

    export API_IMAGE=$REPO/api:v1
    gcloud builds submit --config deploy/gcp/cloudbuild-api.yaml --substitutions=_IMAGE=$API_IMAGE .

    gcloud run deploy guru-api --image $API_IMAGE --region $REGION --port 8080 --allow-unauthenticated \
      --min-instances 1 --max-instances 1 --no-cpu-throttling --cpu 1 --memory 1Gi \
      --add-cloudsql-instances $CONN \
      --set-secrets DATABASE_URL=guru-database-url:latest,OPERATOR_DATABASE_URL=guru-database-url:latest,GURU_SECRET_KEY=guru-secret-key:latest,GURU_ADMIN_PASSWORD=guru-admin-password:latest,GURU_VIEWER_PASSWORD=guru-viewer-password:latest

    export API_URL=$(gcloud run services describe guru-api --region $REGION --format='value(status.url)')
    curl -s $API_URL/api/v1/csrf

You should get `{"token": "..."}`. The first start runs all the database migrations. If it fails:
`gcloud run services logs read guru-api --region $REGION --limit 60`.

Why these flags: **one always-on instance** because the job worker and scheduler run inside the API process and
sessions live in that process's memory (no Redis needed for a single instance; sessions reset when you redeploy).
`OPERATOR_DATABASE_URL` is the owner, because a managed database may refuse the `BYPASSRLS` role.

## 7. Load the demo data (a one-off job)

    gcloud run jobs create guru-seed --image $API_IMAGE --region $REGION --max-retries 0 --task-timeout 900 \
      --add-cloudsql-instances $CONN \
      --set-secrets DATABASE_URL=guru-database-url:latest,OPERATOR_DATABASE_URL=guru-database-url:latest,GURU_SECRET_KEY=guru-secret-key:latest,DEMO_PASSWORD=guru-demo-password:latest \
      --command python --args scripts/seed_demo_bank.py,--reset,--drop-default-workspace
    gcloud run jobs execute guru-seed --region $REGION --wait

It ends with "Seeded 'Lumora Bank' as workspace N". Re-run the last line any time to rebuild the data fresh
(all dates are relative to the day you run it, so do this the evening before a demo).

## 8. Build and start the web app

    export WEB_IMAGE=$REPO/web:v1
    gcloud builds submit --config deploy/gcp/cloudbuild-web.yaml --substitutions=_IMAGE=$WEB_IMAGE,_API_ORIGIN=$API_URL .

    gcloud run deploy guru-web --image $WEB_IMAGE --region $REGION --port 3000 --allow-unauthenticated \
      --min-instances 0 --max-instances 2 --memory 1Gi --set-env-vars GURU_API_ORIGIN=$API_URL

    gcloud run services describe guru-web --region $REGION --format='value(status.url)'

The web build needs the API address at build time (it bakes the `/api` proxy in), which is why the API goes first.

## 9. Check it

Open the web URL, sign in as `demo.admin` with the demo password. You should see **Lumora Bank**, four priorities
on Overview, and the content calendar. Nothing else (no real bank) should be listed in the workspace switcher.

## Things that behave differently in the cloud

- Uploaded images in the content calendar are stored on the container's disk and are lost on redeploy
  (use a Cloud Storage bucket for anything permanent).
- The live "realtime" banner uses a WebSocket that Next's proxy does not carry; pages still load and refresh.
- The AI features call Gemini with `GOOGLE_API_KEY` if you set one, otherwise they use offline text. Moving them to
  Vertex AI is the next change (see `docs/GCP-MIGRATION.md`).

## Teardown (stops the billing)

    gcloud run services delete guru-web guru-api --region $REGION --quiet
    gcloud run jobs delete guru-seed --region $REGION --quiet
    gcloud sql instances delete guru-db --quiet
    gcloud artifacts repositories delete guru --location=$REGION --quiet
    for S in guru-database-url guru-secret-key guru-admin-password guru-viewer-password guru-demo-password; do gcloud secrets delete $S --quiet; done
