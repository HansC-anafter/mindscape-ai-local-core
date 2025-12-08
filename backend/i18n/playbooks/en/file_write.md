# File Write

## Description

Write content to a file in the workspace storage directory.

## Use Cases

- Generate files and write content
- Save text data to files
- Create configuration files or document files

## Input Parameters

- **file_path** (required): Relative file path from workspace storage directory
- **content** (required): File content to write
- **encoding** (optional): File encoding, default is utf-8

## Outputs

- **file_path**: Path of the written file
- **size**: File size in bytes
- **success**: Whether the file write was successful

## Example

Write a test file:

```json
{
  "file_path": "test_file.txt",
  "content": "This is a test file",
  "encoding": "utf-8"
}
```

