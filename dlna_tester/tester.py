"""Core DLNA/UPnP tester implementation."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from lxml import etree

# XML Namespaces used in UPnP/DLNA
NS = {
    "upnp": "urn:schemas-upnp-org:device-1-0",
    "service": "urn:schemas-upnp-org:service-1-0",
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "didl": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "upnp_meta": "urn:schemas-upnp-org:metadata-1-0/upnp/",
    "dlna": "urn:schemas-dlna-org:metadata-1-0/",
}


@dataclass
class ServiceInfo:
    """Information about a UPnP service."""

    service_type: str
    service_id: str
    scpd_url: str
    control_url: str
    event_sub_url: str
    actions: list[str] = field(default_factory=list)
    state_variables: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DeviceInfo:
    """Information about a UPnP device."""

    device_type: str
    friendly_name: str
    manufacturer: str
    manufacturer_url: str | None
    model_name: str
    model_description: str | None
    model_number: str | None
    model_url: str | None
    serial_number: str | None
    udn: str
    presentation_url: str | None
    services: list[ServiceInfo] = field(default_factory=list)
    icons: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MediaItem:
    """Represents a media item from DIDL-Lite."""

    id: str
    parent_id: str
    title: str
    item_class: str
    restricted: bool
    resources: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_container: bool = False
    child_count: int | None = None


class DLNATester:
    """DLNA/UPnP Media Server compliance tester."""

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        """Initialize the tester with server address.

        Args:
            host: Server IP address or hostname
            port: Server port number
            timeout: Request timeout in seconds
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
        self.device_info: DeviceInfo | None = None
        self._device_description_url: str | None = None
        self._content_directory: ServiceInfo | None = None
        self._connection_manager: ServiceInfo | None = None

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self) -> "DLNATester":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _make_url(self, path: str) -> str:
        """Create absolute URL from relative path."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(self.base_url, path)

    def _soap_request(
        self,
        control_url: str,
        service_type: str,
        action: str,
        arguments: dict[str, str] | None = None,
    ) -> etree._Element | None:
        """Send a SOAP request and return the response body.

        Args:
            control_url: The control URL for the service
            service_type: The service type URN
            action: The action name
            arguments: Optional dict of argument name -> value

        Returns:
            The parsed XML response body element, or None on error
        """
        arguments = arguments or {}

        # Build SOAP envelope
        args_xml = "".join(
            f"<{name}>{html.escape(str(value))}</{name}>"
            for name, value in arguments.items()
        )

        soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
    <s:Body>
        <u:{action} xmlns:u="{service_type}">
            {args_xml}
        </u:{action}>
    </s:Body>
</s:Envelope>"""

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service_type}#{action}"',
            "User-Agent": "DLNA-Tester/1.0 UPnP/1.0",
        }

        url = self._make_url(control_url)
        try:
            response = self.client.post(url, content=soap_body, headers=headers)
            response.raise_for_status()
            root = etree.fromstring(response.content)
            body = root.find(".//soap:Body", NS)
            return body
        except Exception:
            return None

    def discover_device_description(self) -> str | None:
        """Try to find the device description URL.

        Returns:
            The device description URL if found, None otherwise
        """
        # Common paths for device description
        common_paths = [
            "/DeviceDescription.xml",
            "/description.xml",
            "/rootDesc.xml",
            "/device.xml",
            "/MediaServer.xml",
            "/dmr.xml",
            "/upnp/desc.xml",
            "/dlna/device.xml",
            "/",
        ]

        for path in common_paths:
            url = self._make_url(path)
            try:
                response = self.client.get(url)
                if response.status_code == 200:
                    content = response.text
                    if "urn:schemas-upnp-org:device" in content:
                        self._device_description_url = url
                        return url
            except Exception:
                continue

        return None

    def fetch_device_description(self, url: str | None = None) -> DeviceInfo | None:
        """Fetch and parse the device description.

        Args:
            url: Optional URL to fetch from. If None, uses discovered URL.

        Returns:
            DeviceInfo if successful, None otherwise
        """
        if url is None:
            url = self._device_description_url
        if url is None:
            url = self.discover_device_description()
        if url is None:
            return None

        try:
            response = self.client.get(url)
            response.raise_for_status()
            root = etree.fromstring(response.content)
        except Exception:
            return None

        device = root.find(".//upnp:device", NS)
        if device is None:
            return None

        def get_text(elem: etree._Element | None, tag: str) -> str:
            child = elem.find(f"upnp:{tag}", NS) if elem is not None else None
            return child.text if child is not None and child.text else ""

        def get_text_optional(elem: etree._Element | None, tag: str) -> str | None:
            child = elem.find(f"upnp:{tag}", NS) if elem is not None else None
            return child.text if child is not None and child.text else None

        # Parse services
        services: list[ServiceInfo] = []
        service_list = device.find("upnp:serviceList", NS)
        if service_list is not None:
            for service_elem in service_list.findall("upnp:service", NS):
                service = ServiceInfo(
                    service_type=get_text(service_elem, "serviceType"),
                    service_id=get_text(service_elem, "serviceId"),
                    scpd_url=get_text(service_elem, "SCPDURL"),
                    control_url=get_text(service_elem, "controlURL"),
                    event_sub_url=get_text(service_elem, "eventSubURL"),
                )
                services.append(service)

        # Parse icons
        icons: list[dict[str, Any]] = []
        icon_list = device.find("upnp:iconList", NS)
        if icon_list is not None:
            for icon_elem in icon_list.findall("upnp:icon", NS):
                icon = {
                    "mimetype": get_text(icon_elem, "mimetype"),
                    "width": get_text(icon_elem, "width"),
                    "height": get_text(icon_elem, "height"),
                    "depth": get_text(icon_elem, "depth"),
                    "url": get_text(icon_elem, "url"),
                }
                icons.append(icon)

        self.device_info = DeviceInfo(
            device_type=get_text(device, "deviceType"),
            friendly_name=get_text(device, "friendlyName"),
            manufacturer=get_text(device, "manufacturer"),
            manufacturer_url=get_text_optional(device, "manufacturerURL"),
            model_name=get_text(device, "modelName"),
            model_description=get_text_optional(device, "modelDescription"),
            model_number=get_text_optional(device, "modelNumber"),
            model_url=get_text_optional(device, "modelURL"),
            serial_number=get_text_optional(device, "serialNumber"),
            udn=get_text(device, "UDN"),
            presentation_url=get_text_optional(device, "presentationURL"),
            services=services,
            icons=icons,
        )

        # Cache important services
        for svc in services:
            if "ContentDirectory" in svc.service_type:
                self._content_directory = svc
            elif "ConnectionManager" in svc.service_type:
                self._connection_manager = svc

        return self.device_info

    def fetch_service_description(self, service: ServiceInfo) -> bool:
        """Fetch and parse the SCPD (Service Control Protocol Description).

        Args:
            service: The service to fetch description for

        Returns:
            True if successful, False otherwise
        """
        url = self._make_url(service.scpd_url)
        try:
            response = self.client.get(url)
            response.raise_for_status()
            root = etree.fromstring(response.content)
        except Exception:
            return False

        # Parse actions
        action_list = root.find(".//service:actionList", NS)
        if action_list is not None:
            for action_elem in action_list.findall("service:action", NS):
                name_elem = action_elem.find("service:name", NS)
                if name_elem is not None and name_elem.text:
                    service.actions.append(name_elem.text)

        # Parse state variables
        state_table = root.find(".//service:serviceStateTable", NS)
        if state_table is not None:
            for var_elem in state_table.findall("service:stateVariable", NS):
                name_elem = var_elem.find("service:name", NS)
                type_elem = var_elem.find("service:dataType", NS)
                if name_elem is not None:
                    var_info = {
                        "name": name_elem.text,
                        "data_type": type_elem.text if type_elem is not None else None,
                        "send_events": var_elem.get("sendEvents", "yes"),
                    }
                    service.state_variables.append(var_info)

        return True

    def get_search_capabilities(self) -> str | None:
        """Get the search capabilities of the Content Directory service.

        Returns:
            The search capabilities string, or None on error
        """
        if self._content_directory is None:
            return None

        body = self._soap_request(
            self._content_directory.control_url,
            self._content_directory.service_type,
            "GetSearchCapabilities",
        )
        if body is None:
            return None

        result = body.find(".//{urn:schemas-upnp-org:service:ContentDirectory:1}SearchCaps")
        if result is None:
            # Try without namespace
            result = body.find(".//SearchCaps")
        return result.text if result is not None else ""

    def get_sort_capabilities(self) -> str | None:
        """Get the sort capabilities of the Content Directory service.

        Returns:
            The sort capabilities string, or None on error
        """
        if self._content_directory is None:
            return None

        body = self._soap_request(
            self._content_directory.control_url,
            self._content_directory.service_type,
            "GetSortCapabilities",
        )
        if body is None:
            return None

        result = body.find(".//{urn:schemas-upnp-org:service:ContentDirectory:1}SortCaps")
        if result is None:
            result = body.find(".//SortCaps")
        return result.text if result is not None else ""

    def get_system_update_id(self) -> int | None:
        """Get the system update ID from the Content Directory service.

        Returns:
            The system update ID, or None on error
        """
        if self._content_directory is None:
            return None

        body = self._soap_request(
            self._content_directory.control_url,
            self._content_directory.service_type,
            "GetSystemUpdateID",
        )
        if body is None:
            return None

        result = body.find(".//{urn:schemas-upnp-org:service:ContentDirectory:1}Id")
        if result is None:
            result = body.find(".//Id")
        try:
            return int(result.text) if result is not None and result.text else None
        except ValueError:
            return None

    def get_protocol_info(self) -> tuple[str | None, str | None]:
        """Get protocol info from the Connection Manager service.

        Returns:
            Tuple of (source protocols, sink protocols), or (None, None) on error
        """
        if self._connection_manager is None:
            return None, None

        body = self._soap_request(
            self._connection_manager.control_url,
            self._connection_manager.service_type,
            "GetProtocolInfo",
        )
        if body is None:
            return None, None

        source = body.find(".//{urn:schemas-upnp-org:service:ConnectionManager:1}Source")
        if source is None:
            source = body.find(".//Source")
        sink = body.find(".//{urn:schemas-upnp-org:service:ConnectionManager:1}Sink")
        if sink is None:
            sink = body.find(".//Sink")

        return (
            source.text if source is not None else None,
            sink.text if sink is not None else None,
        )

    def browse(
        self,
        object_id: str = "0",
        browse_flag: str = "BrowseDirectChildren",
        filter_str: str = "*",
        starting_index: int = 0,
        requested_count: int = 100,
        sort_criteria: str = "",
    ) -> tuple[list[MediaItem], int, int] | None:
        """Browse the Content Directory.

        Args:
            object_id: The object ID to browse (0 for root)
            browse_flag: BrowseDirectChildren or BrowseMetadata
            filter_str: Filter for returned properties (* for all)
            starting_index: Index to start from
            requested_count: Number of items to return (0 for all)
            sort_criteria: Sort criteria

        Returns:
            Tuple of (items, number_returned, total_matches), or None on error
        """
        if self._content_directory is None:
            return None

        body = self._soap_request(
            self._content_directory.control_url,
            self._content_directory.service_type,
            "Browse",
            {
                "ObjectID": object_id,
                "BrowseFlag": browse_flag,
                "Filter": filter_str,
                "StartingIndex": str(starting_index),
                "RequestedCount": str(requested_count),
                "SortCriteria": sort_criteria,
            },
        )
        if body is None:
            return None

        # Extract response values
        ns = "{urn:schemas-upnp-org:service:ContentDirectory:1}"
        result_elem = body.find(f".//{ns}Result")
        if result_elem is None:
            result_elem = body.find(".//Result")

        num_returned_elem = body.find(f".//{ns}NumberReturned")
        if num_returned_elem is None:
            num_returned_elem = body.find(".//NumberReturned")

        total_matches_elem = body.find(f".//{ns}TotalMatches")
        if total_matches_elem is None:
            total_matches_elem = body.find(".//TotalMatches")

        if result_elem is None or result_elem.text is None:
            return [], 0, 0

        try:
            number_returned = (
                int(num_returned_elem.text)
                if num_returned_elem is not None and num_returned_elem.text
                else 0
            )
            total_matches = (
                int(total_matches_elem.text)
                if total_matches_elem is not None and total_matches_elem.text
                else 0
            )
        except ValueError:
            number_returned = 0
            total_matches = 0

        # Parse DIDL-Lite
        items = self._parse_didl_lite(result_elem.text)
        return items, number_returned, total_matches

    def _parse_didl_lite(self, didl_text: str) -> list[MediaItem]:
        """Parse DIDL-Lite XML into MediaItem objects.

        Args:
            didl_text: The DIDL-Lite XML string

        Returns:
            List of MediaItem objects
        """
        items: list[MediaItem] = []

        try:
            # Unescape HTML entities if needed
            if "&lt;" in didl_text:
                didl_text = html.unescape(didl_text)

            root = etree.fromstring(didl_text.encode("utf-8"))
        except Exception:
            return items

        # Process containers
        for container in root.findall(".//didl:container", NS):
            item = self._parse_didl_item(container, is_container=True)
            if item:
                items.append(item)

        # Process items
        for item_elem in root.findall(".//didl:item", NS):
            item = self._parse_didl_item(item_elem, is_container=False)
            if item:
                items.append(item)

        return items

    def _parse_didl_item(
        self, elem: etree._Element, is_container: bool
    ) -> MediaItem | None:
        """Parse a single DIDL-Lite item or container element.

        Args:
            elem: The XML element
            is_container: Whether this is a container

        Returns:
            MediaItem or None on error
        """
        item_id = elem.get("id", "")
        parent_id = elem.get("parentID", "")
        restricted = elem.get("restricted", "1") == "1"

        # Get title
        title_elem = elem.find("dc:title", NS)
        title = title_elem.text if title_elem is not None and title_elem.text else ""

        # Get class
        class_elem = elem.find("upnp_meta:class", NS)
        item_class = (
            class_elem.text if class_elem is not None and class_elem.text else ""
        )

        # Get child count for containers
        child_count = None
        if is_container:
            cc = elem.get("childCount")
            if cc:
                try:
                    child_count = int(cc)
                except ValueError:
                    pass

        # Parse resources
        resources: list[dict[str, Any]] = []
        for res in elem.findall("didl:res", NS):
            res_info: dict[str, Any] = {
                "url": res.text,
                "protocol_info": res.get("protocolInfo"),
                "size": res.get("size"),
                "duration": res.get("duration"),
                "bitrate": res.get("bitrate"),
                "sample_frequency": res.get("sampleFrequency"),
                "bits_per_sample": res.get("bitsPerSample"),
                "nr_audio_channels": res.get("nrAudioChannels"),
                "resolution": res.get("resolution"),
                "color_depth": res.get("colorDepth"),
            }
            # Remove None values
            res_info = {k: v for k, v in res_info.items() if v is not None}
            resources.append(res_info)

        # Parse additional metadata
        metadata: dict[str, Any] = {}

        # Common Dublin Core elements
        for dc_elem in ["creator", "date", "description", "publisher", "rights"]:
            found = elem.find(f"dc:{dc_elem}", NS)
            if found is not None and found.text:
                metadata[dc_elem] = found.text

        # Common UPnP elements
        for upnp_elem in [
            "artist",
            "album",
            "genre",
            "albumArtURI",
            "originalTrackNumber",
            "playbackCount",
            "lastPlaybackTime",
            "rating",
        ]:
            found = elem.find(f"upnp_meta:{upnp_elem}", NS)
            if found is not None and found.text:
                metadata[upnp_elem] = found.text

        return MediaItem(
            id=item_id,
            parent_id=parent_id,
            title=title,
            item_class=item_class,
            restricted=restricted,
            resources=resources,
            metadata=metadata,
            is_container=is_container,
            child_count=child_count,
        )

    def search(
        self,
        container_id: str = "0",
        search_criteria: str = "*",
        filter_str: str = "*",
        starting_index: int = 0,
        requested_count: int = 100,
        sort_criteria: str = "",
    ) -> tuple[list[MediaItem], int, int] | None:
        """Search the Content Directory.

        Args:
            container_id: The container ID to search in (0 for all)
            search_criteria: UPnP search criteria
            filter_str: Filter for returned properties (* for all)
            starting_index: Index to start from
            requested_count: Number of items to return
            sort_criteria: Sort criteria

        Returns:
            Tuple of (items, number_returned, total_matches), or None on error
        """
        if self._content_directory is None:
            return None

        body = self._soap_request(
            self._content_directory.control_url,
            self._content_directory.service_type,
            "Search",
            {
                "ContainerID": container_id,
                "SearchCriteria": search_criteria,
                "Filter": filter_str,
                "StartingIndex": str(starting_index),
                "RequestedCount": str(requested_count),
                "SortCriteria": sort_criteria,
            },
        )
        if body is None:
            return None

        ns = "{urn:schemas-upnp-org:service:ContentDirectory:1}"
        result_elem = body.find(f".//{ns}Result")
        if result_elem is None:
            result_elem = body.find(".//Result")

        num_returned_elem = body.find(f".//{ns}NumberReturned")
        if num_returned_elem is None:
            num_returned_elem = body.find(".//NumberReturned")

        total_matches_elem = body.find(f".//{ns}TotalMatches")
        if total_matches_elem is None:
            total_matches_elem = body.find(".//TotalMatches")

        if result_elem is None or result_elem.text is None:
            return [], 0, 0

        try:
            number_returned = (
                int(num_returned_elem.text)
                if num_returned_elem is not None and num_returned_elem.text
                else 0
            )
            total_matches = (
                int(total_matches_elem.text)
                if total_matches_elem is not None and total_matches_elem.text
                else 0
            )
        except ValueError:
            number_returned = 0
            total_matches = 0

        items = self._parse_didl_lite(result_elem.text)
        return items, number_returned, total_matches

    def fetch_resource(self, url: str) -> tuple[bytes | None, str | None]:
        """Fetch a media resource to verify accessibility.

        Args:
            url: The resource URL

        Returns:
            Tuple of (partial content, content-type), or (None, None) on error
        """
        full_url = self._make_url(url)
        try:
            # Only fetch headers and first few bytes to verify accessibility
            response = self.client.get(
                full_url, headers={"Range": "bytes=0-1023"}, follow_redirects=True
            )
            if response.status_code in (200, 206):
                return response.content, response.headers.get("Content-Type")
        except Exception:
            pass
        return None, None

    def check_resource_headers(self, url: str) -> dict[str, Any]:
        """Check headers for a media resource (HEAD request).

        Args:
            url: The resource URL

        Returns:
            Dict with header information
        """
        full_url = self._make_url(url)
        result: dict[str, Any] = {
            "accessible": False,
            "content_type": None,
            "content_length": None,
            "accept_ranges": None,
            "transfer_mode": None,
        }

        try:
            response = self.client.head(full_url, follow_redirects=True)
            if response.status_code == 200:
                result["accessible"] = True
                result["content_type"] = response.headers.get("Content-Type")
                result["content_length"] = response.headers.get("Content-Length")
                result["accept_ranges"] = response.headers.get("Accept-Ranges")
                result["transfer_mode"] = response.headers.get(
                    "transferMode.dlna.org"
                )
        except Exception:
            pass

        return result
