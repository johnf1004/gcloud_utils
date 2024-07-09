import logging
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from google.cloud import secretmanager
import pandas as pd
from dateutil import parser
import base64
import json
from datetime import datetime, timezone
import google.oauth2.id_token
import google.auth.transport.requests
from google.api_core.exceptions import BadRequest

logger = logging.getLogger(__name__)


def get_most_recent_date(fs, gcs_path, max_date):
    """
    # Function to get most recent datekey (before max_date) of files in a GCS bucket/folder

    :param fs: GCSFileSystem client
    :param gcs_path: Path to check
    :param max_date: Wont look for files after this date
    :return: Most recent datekey of files available
    """

    files = list(fs.walk(gcs_path))[0][2]
    file_dates = [x.split('_')[-1].split('.')[0] for x in files]
    file_dates = [int(x) for x in file_dates if x.isdigit()]
    file_dates = [x for x in file_dates if x < int(max_date)]
    file_dates.sort()
    most_recent_date = file_dates[-1]

    return most_recent_date


def list_files_in_path(fs, gcs_path):
    """

    :param fs: GCSFileSystem client
    :param gcs_path: Path to check
    :return:
    """
    files_list = list(fs.find(gcs_path))
    files_list = [x for x in files_list if x != gcs_path]
    files_list.sort()

    return files_list


def create_cloud_bucket(bucket_name, project_name, storage_client):
    """
    Create cloud bucket

    :param bucket_name: Desired bucket name
    :param project_name: Project name
    :param storage_client: google cloud storage client
    """
    storage_client.create_bucket(bucket_name, project_name)
    logger.info(f'created cloud bucket {bucket_name}')


def create_bq_dataset(dataset_id, bq_client, location='EU'):
    """
    
    :param dataset_id: Name of dataset to create; projectname.datasetname
    :param bq_client: Bigquery client object
    :param location: Location to create dataset
    :return: 
    """
    db = bigquery.Dataset(dataset_id)
    db.location = location
    bq_client.create_dataset(db, timeout=30)


def execute_bigquery_command(sql, bq_client, location='EU'):
    """
    Create function to be used in bigquery commands

    :param sql: Bigquery command to create function
    :param bq_client: bigquery client
    :param location: Location to run the query (table must be in this location)
    """
    query_job = bq_client.query(
        sql,
        location=location,
        job_config=bigquery.QueryJobConfig()
    )
    result = query_job.result()
    return result


def create_bq_table(table_id, partition_col, partition_type, schema, bq_client, partition_expiration=None, expires=None):
    """
    Create partitioned table in bigquery
    :param table_id: Name of table to be created; projectname.datasetname.table
    :param partition_col: Column to partition on
    :param partition_type: bigquery.TimePartitioningType.MONTH or bigquery.TimePartitioningType.DAY,
    :param partition_expiration: Milliseconds until a partition expires 
    :param schema: Schema, list of bigquery.schema.SchemaField objects
    :param bq_client Bigquery client object
    :param expires: Expiration date for the table
    """

    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=partition_type,
        field=partition_col,
        expiration_ms=partition_expiration
    )
    if expires:
        assert isinstance(expires, datetime), "Expiration date must be a datetime object"
        table.expires = expires

    table = bq_client.create_table(table)
    logger.info(
        "Created table {}, partitioned on column {}".format(
            table.table_id, table.time_partitioning.field
        )
    )

def create_bq_table_from_file(file, table_id, field_delimiter, partition_col, partition_type, schema, bq_client, partition_expiration=None):
    """
    Create a bigquery table from a local csv file

    :param file: Local file
    :param table_id: Name of table to be created; projectname.datasetname.table
    :param schema: Schema, list of bigquery.schema.SchemaField objects
    :param field_delimiter: Separator character for csv
    :param bq_client: Bigquery client object
    :param partition_col: Column to use as partition in the table
    """

    # Configure schema
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1, schema=schema,
        write_disposition=bigquery.job.WriteDisposition.WRITE_APPEND,
        field_delimiter=field_delimiter
    )

    if partition_col:
        job_config.time_partitioning = bigquery.TimePartitioning(
            type_=partition_type,
            field=partition_col,
            expiration_ms=partition_expiration)

    # Set up job
    with open(file, "rb") as source_file:
        job = bq_client.load_table_from_file(source_file, table_id, job_config=job_config)

    try:
        job.result()  # Waits for the job to complete.
    except BadRequest:
        logging.error(f"Job failed, errors collection = {job.errors}")
        raise


    table = bq_client.get_table(table_id)  # Make an API request.
    logger.info(
        "Loaded {} rows and {} columns to {}".format(
            table.num_rows, len(table.schema), table_id
        )
    )


def create_bq_table_from_file_json(table_id, schema, bq_client, partition_col=None, file=None, uri=None):
    """
    Create a bigquery table from a local csv file

    :param file: Local file
    :param uri: GCS uri
    :param table_id: Name of table to be created; projectname.datasetname.table
    :param schema: Schema, list of bigquery.schema.SchemaField objects
    :param bq_client: Bigquery client object
    :param partition_col: Column to use as partition in the table
    """

    assert not (file is None and uri is None), 'Either file or uri must be specified'

    # Configure schema
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=schema,
        write_disposition=bigquery.job.WriteDisposition.WRITE_APPEND
    )

    if partition_col:
        job_config.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=partition_col)

    if file:
        # Set up job
        with open(file, "rb") as source_file:
            job = bq_client.load_table_from_file(source_file, table_id, job_config=job_config)
            try:
                job.result()  # Waits for the job to complete.
            except BadRequest:
                logging.error(f"Job failed, errors collection = {job.errors}")
                raise
    elif uri:
        job = bq_client.load_table_from_uri(
            uri,
            table_id,
            location="EU",  # Must match the destination dataset location.
            job_config=job_config,
        )
        try:
            job.result()  # Waits for the job to complete.
        except BadRequest:
            logging.error(f"Job failed, errors collection = {job.errors}")
            raise

    table = bq_client.get_table(table_id)  # Make an API request.
    logger.info(
        "Loaded {} rows and {} columns to {}".format(
            table.num_rows, len(table.schema), table_id
        )
    )


def generate_feature_bq(sql, table_id, bq_client, labels={}, location='EU'):
    """
    :param sql: Bigquery command to execute
    :param table_id: Name of table to be created; projectname.datasetname.table
    :param bq_client: Bigquery client object
    :param labels: Additional labels
    :param location: Location to run the query (default "EU")
    :return:
    """

    # If table does not already exist, set it up with partitioning
    job_config = bigquery.QueryJobConfig(destination=table_id, write_disposition='WRITE_APPEND', labels=labels)
    try:
        bq_client.get_table(table_id)
    except NotFound:
        job_config.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="event_timestamp")

    query_job = bq_client.query(sql, job_config=job_config, location=location)
    query_job.result()


def get_password(pwd_path):
    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(request={"name": pwd_path})
    pwd = response.payload.data.decode("UTF-8")
    return pwd


def download_blob(bucket_name, source_blob_name, destination_file_name, storage_client, tmp=False):
    """Downloads a blob from the bucket."""
    # The ID of your GCS bucket
    # bucket_name = "your-bucket-name"

    # The ID of your GCS object
    # source_blob_name = "storage-object-name"

    # The path to which the file should be downloaded
    # destination_file_name = "local/path/to/file"

    bucket = storage_client.bucket(bucket_name)

    # Construct a client side representation of a blob.
    # Note `Bucket.blob` differs from `Bucket.get_blob` as it doesn't retrieve
    # any content from Google Cloud Storage. As we don't need additional data,
    # using `Bucket.blob` is preferred here.
    blob = bucket.blob(source_blob_name)

    if tmp:
        blob.download_to_filename('/tmp/' + destination_file_name)
    else:
        blob.download_to_filename(destination_file_name)

    print(
        "Downloaded storage object {} from bucket {} to local file {}.".format(
            source_blob_name, bucket_name, destination_file_name
        )
    )


def upload_blob(bucket_name, source_file_name, destination_blob_name, storage_client):
    """Uploads a file to the bucket."""
    # The ID of your GCS bucket
    # bucket_name = "your-bucket-name"
    # The path to your file to upload
    # source_file_name = "local/path/to/file"
    # The ID of your GCS object
    # destination_blob_name = "storage-object-name"

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)

    print(
        "File {} uploaded to {}.".format(
            source_file_name, destination_blob_name
        )
    )


def blob_to_pandas(bucket_name, source_blob_name, destination_file_name, storage_client):
    """

    :param bucket_name: GCS bucket name
    :param source_blob_name: Path to file in bucket
    :param destination_file_name: Path to destination
    :param storage_client: GCS storage client
    :return:
    """
    # Download from GCS
    download_blob(bucket_name, source_blob_name, destination_file_name, storage_client)

    # Read in file
    df = pd.read_csv('/tmp/' + destination_file_name)

    return df


def bucket_blob_file(gcs_file_path):
    """
    Return the bucket name, the path without the bucket, and the filename, given a GCS path
    """
    bucket_name = gcs_file_path.split('/')[0]
    blob_path = gcs_file_path.replace(bucket_name + '/', '')
    file_name = gcs_file_path.split('/')[-1]
    return bucket_name, blob_path, file_name


def get_bq_jobs(since_time, bq_client):
    """
    Useful function to get a history of bigquery jobs and return a dataframe ordered by the most expensive

    :param since_time: Only return jobs run since this time (%Y-%m-%d %H:%M:%S)
    :param bq_client: Bigquery python client
    :return:
    """
    jobs = bq_client.list_jobs()

    jobs_list = []
    for j in jobs:
        try:
            jobs_list.append(j.__dict__['_properties'])
        except:
            pass

    jobs_df = pd.DataFrame(jobs_list)
    jobs_df = pd.concat([jobs_df, pd.json_normalize(jobs_df['statistics'])], axis=1)

    jobs_df['startTime'] = pd.to_datetime(jobs_df['startTime'], unit='ms')
    jobs_df = jobs_df.loc[jobs_df['startTime'] >= since_time, :]
    jobs_df = jobs_df.sort_values('query.totalBytesBilled', ascending=False)
    return jobs_df


def append_rows_bq_json(rows_to_insert, table_id, bq_client, labels):
    """
    Append rows from a list of dictionaries to an existing bigquery table

    :param table_id: Name of the table to insert the rows projectname.datasetname.table
    :param bq_client: Bigquery client object
    :param labels: Extra labels to pass to the job config
    """

    table_ref = bq_client.get_table(table_id)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.job.WriteDisposition.WRITE_APPEND,
        labels=labels
    )

    job = bq_client.load_table_from_json(
        rows_to_insert,
        table_ref,
        job_config=job_config
    )

    try:
        job.result()  # Waits for the job to complete.
    except BadRequest:
        logging.error(f"Job failed, errors collection = {job.errors}")
        raise

    try:
        assert job.state == "DONE"
        logger.info("Data loaded successfully")
    except:
        logger.exception("Error loading data: {}".format(job.errors))
        raise


def append_rows_bq_pandas(df_to_insert, table_id, bq_client, labels):
    """
    Append rows from a pandas dataframe to an existing bigquery table

    :param table_id: Name of the table to insert the dataframe; projectname.datasetname.table
    :param bq_client: Bigquery client object
    :param labels: Extra labels to pass to the job config
    """

    table_ref = bq_client.get_table(table_id)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        write_disposition=bigquery.job.WriteDisposition.WRITE_APPEND,
        labels=labels
    )

    job = bq_client.load_table_from_dataframe(
        df_to_insert,
        table_ref,
        job_config=job_config
    )

    try:
        job.result()  # Waits for the job to complete.
    except BadRequest:
        logging.error(f"Job failed, errors collection = {job.errors}")
        raise
    
    try:
        assert job.state == "DONE"
        logger.info("Data loaded successfully")
    except:
        logger.exception("Error loading data: {}".format(job.errors))
        raise


def cloud_function_prevent_infinite_retries(context, max_age_ms, override_event_time=None):
    """
    Function used in cloud functions which prevents infinite retries. Returns False if event has exceeded maximum threshold set by max_age_ms

    :param context: Context argument from GCP cloud functions
    :param max_age_ms: Time in ms after which the event times out
    :param override_event_time: Gen2 functions dont have context.timestamp. We can supply another event_time to use instead
    """

    # Avoid infinite retries
    if context:
        timestamp = context.timestamp
        if timestamp:
            event_time = parser.parse(timestamp)
        elif override_event_time:
            event_time = parser.parse(override_event_time)
        else:
            logging.warning("No event time available to prevent infinite retries")
            return
    else:
        if override_event_time:
            event_time = parser.parse(override_event_time)
        else:
            logging.warning("Context not available, using datetime.now as event_time to prevent infinite retries (unsafe)")
            event_time = datetime.now(timezone.utc)

    event_age = (datetime.now(timezone.utc) - event_time).total_seconds()
    event_age_ms = event_age * 1000
    
    # Ignore events that are too old
    if event_age_ms > max_age_ms:
        return False
    else:
        return True


def cloud_function_unpack_data(event):
    """
    Function used in cloud functions which extracts the json message payload from pubsub events

    :param event: Pubsub event to trigger GCP cloud functions
    """
    # Verify that the event contains data
    if 'data' in event:
        data = base64.b64decode(event['data']).decode('utf-8')

        # Parse the JSON data in the Pub/Sub message
        try:
            message_data = json.loads(data)
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON data in the message.")
            raise
        return message_data
    else:
        logging.warning("'data' field not found in event")
        return None
    

def cloud_function_eventarc_unpack_labels(event):
    """
    Function used to extract labels from eventarc triggers
    Bigquery jobs can be sent with labels attached. This would be a useful way to pass arguments to cloud functions
    This function extracts those labels

    :param event: Eventarc trigger event for GCP cloud functions
    """

    event_dict = json.loads(event.decode("utf-8"))

    if event_dict.get('severity') == 'ERROR':
        logging.info('error in bigquery job, finishing')
        return
    else:
        job = event_dict['protoPayload']['serviceData']['jobCompletedEvent'].get('job')

        if job:
            if 'jobConfiguration' in job:
                labels = job['jobConfiguration'].get('labels', {})
                return labels
            else:
                logging.warning("No 'jobConfiguration' field in job")
                return
        else:
            logging.warning("No 'job' field found in jobCompletedEvent")
            return


def cloud_function_eventarc_timestamp(event):
    """
    Function used to extract event timestamp from eventarc triggers

    :param event: Eventarc trigger event for GCP cloud functions
    """

    event_dict = json.loads(event.decode("utf-8"))
    return event_dict["receiveTimestamp"]


def cloud_function_eventarc_get_bq_destination(event):
    """
    Function used to assist filtering eventarc triggers, so that function only runs if a specific table is the target of the BQ job
    Standard eventarc filters dont allow you to filter to the table.
    This function returns the dataset name and table name of the events destination table

    :param event: Eventarc trigger event for GCP cloud functions
    """

    event_dict = json.loads(event.decode("utf-8"))

    if event_dict.get('severity') == 'ERROR':
        logging.info('error in bigquery job, finishing')
        return
    else:
        job = event_dict['protoPayload']['serviceData']['jobCompletedEvent'].get('job')

        if job:
            if 'jobConfiguration' in job:
                if 'query' in job['jobConfiguration']:

                    query = job['jobConfiguration']['query']
                    dataset = query['destinationTable']['datasetId']
                    table = query['destinationTable']['tableId']

                    return dataset, table
                
                elif 'load' in job['jobConfiguration']:
                
                    load = job['jobConfiguration']['load']
                    dataset = load['destinationTable']['datasetId']
                    table = load['destinationTable']['tableId']

                    return dataset, table

                else:
                    logging.warning("No 'query' or 'load' field in jobConfiguration")
                    return None, None
            else:
                logging.warning("No 'jobConfiguration' field in job")
                return None, None
        else:
            logging.warning("No 'job' field found in jobCompletedEvent")
            return None, None

def get_gcp_identity_token(audience_url):
    request = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(request, audience_url)
    return id_token


pandas_to_bq_schema = {
    pd.Float64Dtype: 'FLOAT',
    pd.Int64Dtype: 'INTEGER',
    pd.StringDtype: 'STRING',
    pd.BooleanDtype: 'BOOLEAN',
    pd.CategoricalDtype: 'STRING',
    pd.PeriodDtype: 'STRING',
    pd.IntervalDtype: 'STRING',
    pd.Int8Dtype: 'INTEGER',
    pd.Int16Dtype: 'INTEGER',
    pd.Int32Dtype: 'INTEGER',
    pd.Int64Dtype: 'INTEGER',
    pd.UInt8Dtype: 'INTEGER',
    pd.UInt16Dtype: 'INTEGER',
    pd.UInt32Dtype: 'INTEGER',
    pd.UInt64Dtype: 'INTEGER'
}


def update_schema_if_needed(table_id, dataframe, bq_client):
    """
    Function to update the schema of a bigquery table if it is missing columns

    :param table_id: Name of the table to update; projectname.datasetname.table
    :param dataframe: Pandas dataframe which needs to be uploaded
    :param bq_client: Bigquery client object
    """

    table = bq_client.get_table(table_id)
    schema = table.schema
    names = [x.name for x in schema]
    new_columns = [x for x in dataframe.columns if x not in names]
    
    if len(new_columns) > 0:
        new_column_types = [pandas_to_bq_schema[type(dataframe[x].dtype)] for x in new_columns]
        
        new_columns_schemas = [bigquery.SchemaField(new_columns[i], new_column_types[i]) for i in range(len(new_columns))]
        
        new_schema = schema + new_columns_schemas
        table.schema = new_schema
        bq_client.update_table(table, ["schema"])
        
        logger.info(f"Added columns {new_columns} to schema")
        
    removed_columns = [x for x in names if x not in dataframe.columns]
    
    if len(removed_columns) > 0:
        for col_to_remove in removed_columns:
            try:
                drop_qry = "ALTER TABLE `racing_db.variable_monitoring` DROP COLUMN " + col_to_remove
                bq_client.query(drop_qry).result()
                logger.info("Dropped column: ", col_to_remove)
            except BadRequest:
                logger.info(f"Column {col_to_remove} not found so cannot be dropped")
        
    return