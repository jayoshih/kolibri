import csv
import logging
import os

from .constants import drivetypes

logger = logging.getLogger(__name__)

_DRIVE_TYPES = [drivetypes.UNKNOWN, "#noroot", drivetypes.USB_DEVICE, drivetypes.INTERNAL_DRIVE, drivetypes.NETWORK_DRIVE, drivetypes.OPTICAL_DRIVE, "#ram"]

def get_drive_list():

    drives = []

    drive_list = _parse_wmic_csv_output(os.popen('wmic logicaldisk list full /format:csv').read())

    for drive in drive_list:

        # look up the drive type name
        drivetype = _DRIVE_TYPES[int(drive.get("DriveType") or "0")]

        # skip drives that have invalid types
        if drivetype.startswith("#"):
            logger.debug("Skipping drive '{}' with invalid type: {}".format(drive.get("DeviceID"), drivetype))
            continue

        # construct a path (including "\") from DeviceID, plus fallbacks in case it's not defined for some reason
        path = "{}\\".format(drive.get("DeviceID") or drive.get("Caption") or drive.get("Name"))

        # skip if we don't have read access to the drive
        if not os.access(path, os.R_OK):
            continue

        # combine the metadata, using backup fields for missing pieces, and return
        drives.append({
            "path": path,
            "name": drive.get("VolumeName") or drive.get("Description"),
            "filesystem": drive.get("FileSystem").lower(),
            "freespace": int(drive.get("FreeSpace") or 0),
            "totalspace": int(drive.get("Size") or 0),
            "drivetype": drivetype,
            "guid": drive.get("VolumeSerialNumber"),
        })

    return drives

def _parse_wmic_csv_output(text):
    """
    Parse the output of Windows "wmic logicaldisk list full /format:csv" command.
    """

    # parse out the comma-separated values of each non-empty row
    rows = [row for row in csv.reader(text.split("\n")) if row]

    # use the first row as the header row
    header = rows.pop(0)

    # turn each row into a dict, mapping the header text of each column to the row's value for that column
    return [dict(zip(header, row)) for row in rows]
