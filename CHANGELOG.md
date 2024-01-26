# Changelog

# [0.7.0](https://github.com/johnf1004/google_cloud_utilities/compare/v0.6.0...v0.7.0) (2024-01-26)

### Features

* New function get_gcp_identity_token using subprocess, useful for making cloud run calls

### Bug fixes

* download_blob function doesn't force download to /tmp anymore, can specify tmp=False

# [0.6.0](https://github.com/johnf1004/google_cloud_utilities/compare/v0.5.0...v0.6.0) (2023-12-14)

### Features

* New function append_rows_bq_pandas for smoother way to insert rows to table with pandas (with labels in job config)

# [0.5.0](https://github.com/johnf1004/google_cloud_utilities/compare/v0.4.4...v0.5.0) (2023-12-13)

### Features

* New function append_rows_bq_json for smoother way to insert rows to table with dictionaries (with labels in job config)

# [0.4.4](https://github.com/johnf1004/google_cloud_utilities/compare/v0.4.3...v0.4.4) (2023-12-12)

### Bug fixes

* Bug fix in cloud_function_eventarc_get_bq_destination

# [0.4.3](https://github.com/johnf1004/google_cloud_utilities/compare/v0.4.2...v0.4.3) (2023-12-11)

### Bug fixes

* cloud_function_eventarc_get_bq_destination messages with no "query" field will work if they have "load" field

# [0.4.2](https://github.com/johnf1004/google_cloud_utilities/compare/v0.4.1...v0.4.2) (2023-12-06)

### Bug fixes

* cloud_function_prevent_infinite_retries attempts to use override_event_time if context is empty dict or None

# [0.4.1](https://github.com/johnf1004/google_cloud_utilities/compare/v0.4.0...v0.4.1) (2023-12-06)

### Bug fixes

* cloud_function_eventarc_get_bq_destination returns tuple of two Nones instead of single None if missing fields

# [0.4.0](https://github.com/johnf1004/google_cloud_utilities/compare/v0.3.0...v0.4.0) (2023-12-06)

### Features

* Added function for eventarc cloud_function_eventarc_timestamp which gets timestamp from eventarc trigger

# [0.3.0](https://github.com/johnf1004/google_cloud_utilities/compare/v0.2.1...v0.3.0) (2023-12-06)

### Features

* Added function for eventarc cloud_function_eventarc_unpack_labels which extracts labels from the triggering BQ job

# [0.2.1](https://github.com/johnf1004/google_cloud_utilities/compare/v0.2.0...v0.2.1) (2023-12-05)

### Bug fixes

* Added option to override the event time in cloud_function_prevent_infinite_retries (useful for gen2 cloud functions)

# [0.2.0](https://github.com/johnf1004/google_cloud_utilities/compare/v0.1.0...v0.2.0) (2023-12-05)

### Features

* Added function for eventarc cloud_function_eventarc_get_bq_destination

# [0.1.0](https://github.com/johnf1004/google_cloud_utilities/compare/v0.0.6...v0.1.0) (2023-12-05)

### Features

* Added cloud function utilities
