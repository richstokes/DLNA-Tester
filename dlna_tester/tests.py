"""DLNA/UPnP compliance test suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .tester import DLNATester, MediaItem


class TestStatus(Enum):
    """Status of a test result."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class TestCategory(Enum):
    """Categories of compliance tests."""

    CONNECTIVITY = "Connectivity"
    DEVICE_DESCRIPTION = "Device Description"
    CONTENT_DIRECTORY = "Content Directory"
    CONNECTION_MANAGER = "Connection Manager"
    BROWSING = "Browsing"
    METADATA = "Metadata"
    MEDIA_RESOURCES = "Media Resources"
    PROTOCOL_COMPLIANCE = "Protocol Compliance"


@dataclass
class TestResult:
    """Result of a single compliance test."""

    name: str
    category: TestCategory
    status: TestStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0  # Weight for scoring (1.0 = normal, 2.0 = important)

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASS

    @property
    def score(self) -> float:
        """Return score contribution (0.0 to weight)."""
        if self.status == TestStatus.PASS:
            return self.weight
        elif self.status == TestStatus.WARN:
            return self.weight * 0.5
        return 0.0


class TestSuite:
    """DLNA/UPnP compliance test suite."""

    def __init__(self, tester: DLNATester, verbose: bool = False):
        """Initialize the test suite.

        Args:
            tester: The DLNATester instance to use
            verbose: Whether to print verbose output during tests
        """
        self.tester = tester
        self.verbose = verbose
        self.results: list[TestResult] = []
        self._browsed_items: list[MediaItem] = []
        self._max_depth = 3  # Max depth for recursive browsing tests

    def log(self, message: str) -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(f"  → {message}")

    def run_all_tests(self) -> list[TestResult]:
        """Run all compliance tests.

        Returns:
            List of all test results
        """
        self.results = []

        # Run tests in order of dependency
        self._run_connectivity_tests()
        self._run_device_description_tests()
        self._run_content_directory_tests()
        self._run_connection_manager_tests()
        self._run_browsing_tests()
        self._run_metadata_tests()
        self._run_media_resource_tests()
        self._run_protocol_compliance_tests()

        return self.results

    def get_score(self) -> tuple[float, float, str]:
        """Calculate the overall compliance score.

        Returns:
            Tuple of (score, max_score, grade)
        """
        total_score = sum(r.score for r in self.results)
        max_score = sum(r.weight for r in self.results if r.status != TestStatus.SKIP)

        if max_score == 0:
            percentage = 0.0
        else:
            percentage = (total_score / max_score) * 100

        # Determine grade
        if percentage >= 95:
            grade = "A+"
        elif percentage >= 90:
            grade = "A"
        elif percentage >= 85:
            grade = "B+"
        elif percentage >= 80:
            grade = "B"
        elif percentage >= 75:
            grade = "C+"
        elif percentage >= 70:
            grade = "C"
        elif percentage >= 60:
            grade = "D"
        else:
            grade = "F"

        return total_score, max_score, grade

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of test results.

        Returns:
            Dictionary with summary statistics
        """
        passed = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        warned = sum(1 for r in self.results if r.status == TestStatus.WARN)
        skipped = sum(1 for r in self.results if r.status == TestStatus.SKIP)

        by_category: dict[str, dict[str, int]] = {}
        for r in self.results:
            cat = r.category.value
            if cat not in by_category:
                by_category[cat] = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
            by_category[cat][r.status.value.lower()] += 1

        score, max_score, grade = self.get_score()

        return {
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "score": score,
            "max_score": max_score,
            "percentage": (score / max_score * 100) if max_score > 0 else 0,
            "grade": grade,
            "by_category": by_category,
        }

    def _add_result(
        self,
        name: str,
        category: TestCategory,
        status: TestStatus,
        message: str,
        details: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> TestResult:
        """Add a test result."""
        result = TestResult(
            name=name,
            category=category,
            status=status,
            message=message,
            details=details or {},
            weight=weight,
        )
        self.results.append(result)
        return result

    # =========================================================================
    # Connectivity Tests
    # =========================================================================

    def _run_connectivity_tests(self) -> None:
        """Run basic connectivity tests."""
        self.log("Testing connectivity...")

        # Test: Basic HTTP connection
        try:
            response = self.tester.client.get(self.tester.base_url, timeout=5.0)
            self._add_result(
                "HTTP Connection",
                TestCategory.CONNECTIVITY,
                TestStatus.PASS,
                f"Server responded with status {response.status_code}",
                {"status_code": response.status_code},
                weight=2.0,
            )
        except Exception as e:
            self._add_result(
                "HTTP Connection",
                TestCategory.CONNECTIVITY,
                TestStatus.FAIL,
                f"Failed to connect: {e}",
                weight=2.0,
            )
            return  # Can't continue without connectivity

        # Test: Device description discovery
        desc_url = self.tester.discover_device_description()
        if desc_url:
            self._add_result(
                "Device Description Discovery",
                TestCategory.CONNECTIVITY,
                TestStatus.PASS,
                f"Found device description at {desc_url}",
                {"url": desc_url},
                weight=2.0,
            )
        else:
            self._add_result(
                "Device Description Discovery",
                TestCategory.CONNECTIVITY,
                TestStatus.FAIL,
                "Could not find device description XML",
                weight=2.0,
            )

    # =========================================================================
    # Device Description Tests
    # =========================================================================

    def _run_device_description_tests(self) -> None:
        """Run device description compliance tests."""
        self.log("Testing device description...")

        device = self.tester.fetch_device_description()
        if device is None:
            self._add_result(
                "Device Description Parsing",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.FAIL,
                "Could not parse device description",
                weight=2.0,
            )
            return

        # Test: Device type is MediaServer
        if "MediaServer" in device.device_type:
            self._add_result(
                "Device Type",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.PASS,
                f"Device type: {device.device_type}",
                {"device_type": device.device_type},
            )
        else:
            self._add_result(
                "Device Type",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.WARN,
                f"Non-standard device type: {device.device_type}",
                {"device_type": device.device_type},
            )

        # Test: Required fields present
        required_fields = [
            ("friendlyName", device.friendly_name),
            ("manufacturer", device.manufacturer),
            ("modelName", device.model_name),
            ("UDN", device.udn),
        ]

        for field_name, value in required_fields:
            if value:
                self._add_result(
                    f"Required Field: {field_name}",
                    TestCategory.DEVICE_DESCRIPTION,
                    TestStatus.PASS,
                    f"{field_name} present: {value[:50]}..." if len(value) > 50 else f"{field_name} present: {value}",
                )
            else:
                self._add_result(
                    f"Required Field: {field_name}",
                    TestCategory.DEVICE_DESCRIPTION,
                    TestStatus.FAIL,
                    f"Missing required field: {field_name}",
                )

        # Test: UDN format (should be uuid:...)
        if device.udn.startswith("uuid:"):
            self._add_result(
                "UDN Format",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.PASS,
                "UDN follows uuid: format",
            )
        else:
            self._add_result(
                "UDN Format",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.WARN,
                f"UDN does not follow uuid: format: {device.udn}",
            )

        # Test: Services present
        service_types = [s.service_type for s in device.services]
        has_content_dir = any("ContentDirectory" in s for s in service_types)
        has_conn_mgr = any("ConnectionManager" in s for s in service_types)

        if has_content_dir:
            self._add_result(
                "ContentDirectory Service",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.PASS,
                "ContentDirectory service present",
                weight=2.0,
            )
        else:
            self._add_result(
                "ContentDirectory Service",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.FAIL,
                "ContentDirectory service missing (required for DLNA DMS)",
                weight=2.0,
            )

        if has_conn_mgr:
            self._add_result(
                "ConnectionManager Service",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.PASS,
                "ConnectionManager service present",
                weight=1.5,
            )
        else:
            self._add_result(
                "ConnectionManager Service",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.WARN,
                "ConnectionManager service missing (recommended)",
                weight=1.5,
            )

        # Test: Icons present (recommended)
        if device.icons:
            self._add_result(
                "Device Icons",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.PASS,
                f"Device has {len(device.icons)} icon(s)",
                {"icon_count": len(device.icons)},
            )
        else:
            self._add_result(
                "Device Icons",
                TestCategory.DEVICE_DESCRIPTION,
                TestStatus.WARN,
                "No device icons defined (recommended for better UX)",
            )

    # =========================================================================
    # Content Directory Service Tests
    # =========================================================================

    def _run_content_directory_tests(self) -> None:
        """Run Content Directory service tests."""
        self.log("Testing Content Directory service...")

        if self.tester._content_directory is None:
            self._add_result(
                "Content Directory Available",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.SKIP,
                "ContentDirectory service not available",
            )
            return

        cd = self.tester._content_directory

        # Test: Fetch SCPD
        if self.tester.fetch_service_description(cd):
            self._add_result(
                "SCPD Retrieval",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.PASS,
                f"Retrieved SCPD with {len(cd.actions)} actions",
                {"actions": cd.actions},
            )
        else:
            self._add_result(
                "SCPD Retrieval",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.FAIL,
                "Could not retrieve Service Control Protocol Description",
            )

        # Test: Required actions present
        required_actions = ["Browse", "GetSearchCapabilities", "GetSortCapabilities", "GetSystemUpdateID"]
        for action in required_actions:
            if action in cd.actions:
                self._add_result(
                    f"Action: {action}",
                    TestCategory.CONTENT_DIRECTORY,
                    TestStatus.PASS,
                    f"{action} action available",
                )
            else:
                self._add_result(
                    f"Action: {action}",
                    TestCategory.CONTENT_DIRECTORY,
                    TestStatus.FAIL,
                    f"Required action {action} not found",
                )

        # Test: Optional but recommended actions
        optional_actions = ["Search", "CreateObject", "DestroyObject", "UpdateObject"]
        for action in optional_actions:
            if action in cd.actions:
                self._add_result(
                    f"Optional Action: {action}",
                    TestCategory.CONTENT_DIRECTORY,
                    TestStatus.PASS,
                    f"{action} action available",
                    weight=0.5,
                )

        # Test: GetSearchCapabilities
        search_caps = self.tester.get_search_capabilities()
        if search_caps is not None:
            self._add_result(
                "GetSearchCapabilities",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.PASS,
                f"Search capabilities: {search_caps[:100]}..." if search_caps and len(search_caps) > 100 else f"Search capabilities: {search_caps or '(empty)'}",
                {"capabilities": search_caps},
            )
        else:
            self._add_result(
                "GetSearchCapabilities",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.FAIL,
                "GetSearchCapabilities action failed",
            )

        # Test: GetSortCapabilities
        sort_caps = self.tester.get_sort_capabilities()
        if sort_caps is not None:
            self._add_result(
                "GetSortCapabilities",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.PASS,
                f"Sort capabilities: {sort_caps[:100]}..." if sort_caps and len(sort_caps) > 100 else f"Sort capabilities: {sort_caps or '(empty)'}",
                {"capabilities": sort_caps},
            )
        else:
            self._add_result(
                "GetSortCapabilities",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.FAIL,
                "GetSortCapabilities action failed",
            )

        # Test: GetSystemUpdateID
        update_id = self.tester.get_system_update_id()
        if update_id is not None:
            self._add_result(
                "GetSystemUpdateID",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.PASS,
                f"System update ID: {update_id}",
                {"update_id": update_id},
            )
        else:
            self._add_result(
                "GetSystemUpdateID",
                TestCategory.CONTENT_DIRECTORY,
                TestStatus.FAIL,
                "GetSystemUpdateID action failed",
            )

    # =========================================================================
    # Connection Manager Tests
    # =========================================================================

    def _run_connection_manager_tests(self) -> None:
        """Run Connection Manager service tests."""
        self.log("Testing Connection Manager service...")

        if self.tester._connection_manager is None:
            self._add_result(
                "Connection Manager Available",
                TestCategory.CONNECTION_MANAGER,
                TestStatus.SKIP,
                "ConnectionManager service not available",
            )
            return

        cm = self.tester._connection_manager

        # Test: Fetch SCPD
        if self.tester.fetch_service_description(cm):
            self._add_result(
                "CM SCPD Retrieval",
                TestCategory.CONNECTION_MANAGER,
                TestStatus.PASS,
                f"Retrieved SCPD with {len(cm.actions)} actions",
                {"actions": cm.actions},
            )
        else:
            self._add_result(
                "CM SCPD Retrieval",
                TestCategory.CONNECTION_MANAGER,
                TestStatus.FAIL,
                "Could not retrieve ConnectionManager SCPD",
            )

        # Test: GetProtocolInfo
        source, sink = self.tester.get_protocol_info()
        if source is not None:
            protocols = source.split(",") if source else []
            self._add_result(
                "GetProtocolInfo",
                TestCategory.CONNECTION_MANAGER,
                TestStatus.PASS,
                f"Source protocols: {len(protocols)} defined",
                {"source_protocols": protocols[:10], "total_count": len(protocols)},
            )

            # Check for common DLNA protocols
            has_http = any("http-get" in p.lower() for p in protocols)
            if has_http:
                self._add_result(
                    "HTTP Streaming Protocol",
                    TestCategory.CONNECTION_MANAGER,
                    TestStatus.PASS,
                    "http-get protocol supported",
                )
            else:
                self._add_result(
                    "HTTP Streaming Protocol",
                    TestCategory.CONNECTION_MANAGER,
                    TestStatus.WARN,
                    "http-get protocol not advertised",
                )
        else:
            self._add_result(
                "GetProtocolInfo",
                TestCategory.CONNECTION_MANAGER,
                TestStatus.FAIL,
                "GetProtocolInfo action failed",
            )

    # =========================================================================
    # Browsing Tests
    # =========================================================================

    def _run_browsing_tests(self) -> None:
        """Run content browsing tests."""
        self.log("Testing browsing functionality...")

        if self.tester._content_directory is None:
            self._add_result(
                "Browse Root",
                TestCategory.BROWSING,
                TestStatus.SKIP,
                "ContentDirectory not available",
            )
            return

        # Test: Browse root container (ObjectID = 0)
        result = self.tester.browse("0", "BrowseDirectChildren")
        if result is not None:
            items, num_returned, total_matches = result
            self._add_result(
                "Browse Root",
                TestCategory.BROWSING,
                TestStatus.PASS,
                f"Root browse returned {num_returned} items, {total_matches} total",
                {"items": len(items), "num_returned": num_returned, "total_matches": total_matches},
                weight=2.0,
            )
            self._browsed_items.extend(items)

            # Test: Browse metadata for root
            meta_result = self.tester.browse("0", "BrowseMetadata")
            if meta_result is not None:
                self._add_result(
                    "Browse Metadata",
                    TestCategory.BROWSING,
                    TestStatus.PASS,
                    "BrowseMetadata for root successful",
                )
            else:
                self._add_result(
                    "Browse Metadata",
                    TestCategory.BROWSING,
                    TestStatus.FAIL,
                    "BrowseMetadata for root failed",
                )

            # Test: Pagination
            if total_matches > 1:
                page_result = self.tester.browse("0", "BrowseDirectChildren", "*", 0, 1)
                if page_result is not None and page_result[1] == 1:
                    self._add_result(
                        "Pagination Support",
                        TestCategory.BROWSING,
                        TestStatus.PASS,
                        "Pagination (RequestedCount) works correctly",
                    )
                else:
                    self._add_result(
                        "Pagination Support",
                        TestCategory.BROWSING,
                        TestStatus.WARN,
                        "Pagination may not work correctly",
                    )

            # Test: Browse into containers
            containers = [i for i in items if i.is_container]
            if containers:
                self.log(f"Found {len(containers)} containers, testing recursive browse...")
                self._test_recursive_browse(containers[0], depth=1)
            else:
                self._add_result(
                    "Container Navigation",
                    TestCategory.BROWSING,
                    TestStatus.WARN,
                    "No containers found in root to test navigation",
                )

        else:
            self._add_result(
                "Browse Root",
                TestCategory.BROWSING,
                TestStatus.FAIL,
                "Browse action failed for root container",
                weight=2.0,
            )

    def _test_recursive_browse(self, container: MediaItem, depth: int) -> None:
        """Recursively test browsing containers."""
        if depth > self._max_depth:
            return

        result = self.tester.browse(container.id, "BrowseDirectChildren")
        if result is not None:
            items, num_returned, total_matches = result
            self._browsed_items.extend(items)

            if depth == 1:
                self._add_result(
                    "Container Navigation",
                    TestCategory.BROWSING,
                    TestStatus.PASS,
                    f"Successfully browsed container '{container.title}' ({num_returned} items)",
                )

            # Test one more level if containers exist
            sub_containers = [i for i in items if i.is_container]
            if sub_containers and depth < self._max_depth:
                self._test_recursive_browse(sub_containers[0], depth + 1)
        else:
            self._add_result(
                "Container Navigation",
                TestCategory.BROWSING,
                TestStatus.FAIL,
                f"Failed to browse container '{container.title}' (ID: {container.id})",
            )

    # =========================================================================
    # Metadata Tests
    # =========================================================================

    def _run_metadata_tests(self) -> None:
        """Run metadata compliance tests."""
        self.log("Testing metadata compliance...")

        if not self._browsed_items:
            self._add_result(
                "Metadata Availability",
                TestCategory.METADATA,
                TestStatus.SKIP,
                "No items available for metadata testing",
            )
            return

        # Separate containers and items
        containers = [i for i in self._browsed_items if i.is_container]
        media_items = [i for i in self._browsed_items if not i.is_container]

        # Test: All items have required attributes
        items_with_id = sum(1 for i in self._browsed_items if i.id)
        items_with_title = sum(1 for i in self._browsed_items if i.title)
        items_with_class = sum(1 for i in self._browsed_items if i.item_class)

        total = len(self._browsed_items)
        if items_with_id == total:
            self._add_result(
                "Item IDs",
                TestCategory.METADATA,
                TestStatus.PASS,
                f"All {total} items have IDs",
            )
        else:
            self._add_result(
                "Item IDs",
                TestCategory.METADATA,
                TestStatus.FAIL,
                f"{total - items_with_id}/{total} items missing IDs",
            )

        if items_with_title == total:
            self._add_result(
                "Item Titles",
                TestCategory.METADATA,
                TestStatus.PASS,
                f"All {total} items have titles",
            )
        else:
            self._add_result(
                "Item Titles",
                TestCategory.METADATA,
                TestStatus.WARN,
                f"{total - items_with_title}/{total} items missing titles",
            )

        if items_with_class == total:
            self._add_result(
                "Item Classes",
                TestCategory.METADATA,
                TestStatus.PASS,
                f"All {total} items have UPnP classes",
            )
        else:
            self._add_result(
                "Item Classes",
                TestCategory.METADATA,
                TestStatus.WARN,
                f"{total - items_with_class}/{total} items missing UPnP class",
            )

        # Test: Container childCount attribute
        if containers:
            with_child_count = sum(1 for c in containers if c.child_count is not None)
            if with_child_count == len(containers):
                self._add_result(
                    "Container childCount",
                    TestCategory.METADATA,
                    TestStatus.PASS,
                    f"All {len(containers)} containers have childCount",
                )
            else:
                self._add_result(
                    "Container childCount",
                    TestCategory.METADATA,
                    TestStatus.WARN,
                    f"{len(containers) - with_child_count}/{len(containers)} containers missing childCount",
                )

        # Test: Media items have resources
        if media_items:
            with_resources = sum(1 for i in media_items if i.resources)
            if with_resources == len(media_items):
                self._add_result(
                    "Media Resources",
                    TestCategory.METADATA,
                    TestStatus.PASS,
                    f"All {len(media_items)} media items have resources",
                )
            elif with_resources > 0:
                self._add_result(
                    "Media Resources",
                    TestCategory.METADATA,
                    TestStatus.WARN,
                    f"{len(media_items) - with_resources}/{len(media_items)} media items missing resources",
                )
            else:
                self._add_result(
                    "Media Resources",
                    TestCategory.METADATA,
                    TestStatus.FAIL,
                    "No media items have resources defined",
                )

            # Test: Resources have protocolInfo
            all_resources = [r for i in media_items for r in i.resources]
            if all_resources:
                with_protocol_info = sum(1 for r in all_resources if r.get("protocol_info"))
                if with_protocol_info == len(all_resources):
                    self._add_result(
                        "Resource protocolInfo",
                        TestCategory.METADATA,
                        TestStatus.PASS,
                        f"All {len(all_resources)} resources have protocolInfo",
                    )
                else:
                    self._add_result(
                        "Resource protocolInfo",
                        TestCategory.METADATA,
                        TestStatus.WARN,
                        f"{len(all_resources) - with_protocol_info}/{len(all_resources)} resources missing protocolInfo",
                    )

        # Test: UPnP class format
        classes = set(i.item_class for i in self._browsed_items if i.item_class)
        valid_classes = [c for c in classes if c.startswith("object.")]
        if len(valid_classes) == len(classes) and classes:
            self._add_result(
                "UPnP Class Format",
                TestCategory.METADATA,
                TestStatus.PASS,
                f"All classes follow object.* format: {', '.join(list(classes)[:5])}",
            )
        elif valid_classes:
            self._add_result(
                "UPnP Class Format",
                TestCategory.METADATA,
                TestStatus.WARN,
                f"Some classes don't follow object.* format",
                {"valid": valid_classes, "invalid": list(classes - set(valid_classes))},
            )

    # =========================================================================
    # Media Resource Tests
    # =========================================================================

    def _run_media_resource_tests(self) -> None:
        """Run media resource accessibility tests."""
        self.log("Testing media resource accessibility...")

        media_items = [i for i in self._browsed_items if not i.is_container and i.resources]
        if not media_items:
            self._add_result(
                "Resource Accessibility",
                TestCategory.MEDIA_RESOURCES,
                TestStatus.SKIP,
                "No media items with resources available for testing",
            )
            return

        # Test a sample of resources (up to 5)
        test_items = media_items[:5]
        accessible_count = 0
        total_tested = 0

        for item in test_items:
            for res in item.resources[:1]:  # Test first resource of each item
                url = res.get("url")
                if not url:
                    continue

                total_tested += 1
                headers = self.tester.check_resource_headers(url)

                if headers["accessible"]:
                    accessible_count += 1

        if total_tested > 0:
            if accessible_count == total_tested:
                self._add_result(
                    "Resource Accessibility",
                    TestCategory.MEDIA_RESOURCES,
                    TestStatus.PASS,
                    f"All {total_tested} tested resources are accessible",
                    weight=1.5,
                )
            elif accessible_count > 0:
                self._add_result(
                    "Resource Accessibility",
                    TestCategory.MEDIA_RESOURCES,
                    TestStatus.WARN,
                    f"{accessible_count}/{total_tested} tested resources are accessible",
                    weight=1.5,
                )
            else:
                self._add_result(
                    "Resource Accessibility",
                    TestCategory.MEDIA_RESOURCES,
                    TestStatus.FAIL,
                    f"None of {total_tested} tested resources are accessible",
                    weight=1.5,
                )

        # Test: Range request support (important for seeking)
        for item in test_items[:1]:
            for res in item.resources[:1]:
                url = res.get("url")
                if not url:
                    continue

                content, content_type = self.tester.fetch_resource(url)
                if content is not None:
                    self._add_result(
                        "Range Request Support",
                        TestCategory.MEDIA_RESOURCES,
                        TestStatus.PASS,
                        "Server supports partial content requests",
                    )
                else:
                    self._add_result(
                        "Range Request Support",
                        TestCategory.MEDIA_RESOURCES,
                        TestStatus.WARN,
                        "Server may not support range requests (seeking might not work)",
                    )
                break

    # =========================================================================
    # Protocol Compliance Tests
    # =========================================================================

    def _run_protocol_compliance_tests(self) -> None:
        """Run general protocol compliance tests."""
        self.log("Testing protocol compliance...")

        # Test: SOAP fault handling (send invalid request)
        if self.tester._content_directory:
            body = self.tester._soap_request(
                self.tester._content_directory.control_url,
                self.tester._content_directory.service_type,
                "Browse",
                {"ObjectID": "INVALID_ID_THAT_SHOULD_NOT_EXIST_12345"},
            )
            # A compliant server should handle this gracefully
            # Either return empty result or SOAP fault
            self._add_result(
                "Error Handling",
                TestCategory.PROTOCOL_COMPLIANCE,
                TestStatus.PASS if body is not None else TestStatus.WARN,
                "Server handles invalid requests gracefully" if body else "Server may not handle invalid requests gracefully",
            )

        # Test: HTTP HEAD support
        if self.tester._device_description_url:
            try:
                response = self.tester.client.head(self.tester._device_description_url)
                if response.status_code == 200:
                    self._add_result(
                        "HTTP HEAD Support",
                        TestCategory.PROTOCOL_COMPLIANCE,
                        TestStatus.PASS,
                        "Server supports HTTP HEAD requests",
                    )
                else:
                    self._add_result(
                        "HTTP HEAD Support",
                        TestCategory.PROTOCOL_COMPLIANCE,
                        TestStatus.WARN,
                        f"HTTP HEAD returned status {response.status_code}",
                    )
            except Exception:
                self._add_result(
                    "HTTP HEAD Support",
                    TestCategory.PROTOCOL_COMPLIANCE,
                    TestStatus.WARN,
                    "Server may not support HTTP HEAD requests",
                )

        # Test: Content-Type headers
        if self.tester._device_description_url:
            try:
                response = self.tester.client.get(self.tester._device_description_url)
                content_type = response.headers.get("Content-Type", "")
                if "xml" in content_type.lower():
                    self._add_result(
                        "XML Content-Type",
                        TestCategory.PROTOCOL_COMPLIANCE,
                        TestStatus.PASS,
                        f"Correct Content-Type for XML: {content_type}",
                    )
                else:
                    self._add_result(
                        "XML Content-Type",
                        TestCategory.PROTOCOL_COMPLIANCE,
                        TestStatus.WARN,
                        f"Non-standard Content-Type for XML: {content_type}",
                    )
            except Exception:
                pass

        # Test: Consistent SystemUpdateID
        if self.tester._content_directory:
            id1 = self.tester.get_system_update_id()
            id2 = self.tester.get_system_update_id()
            if id1 is not None and id2 is not None:
                if id1 == id2:
                    self._add_result(
                        "SystemUpdateID Consistency",
                        TestCategory.PROTOCOL_COMPLIANCE,
                        TestStatus.PASS,
                        "SystemUpdateID is consistent between requests",
                    )
                else:
                    self._add_result(
                        "SystemUpdateID Consistency",
                        TestCategory.PROTOCOL_COMPLIANCE,
                        TestStatus.WARN,
                        f"SystemUpdateID changed between requests: {id1} -> {id2}",
                    )
