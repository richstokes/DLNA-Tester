"""Command-line interface for DLNA tester."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from .tester import DLNATester
from .tests import TestCategory, TestStatus, TestSuite


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


def colorize(text: str, color: str) -> str:
    """Apply ANSI color to text."""
    return f"{color}{text}{Colors.RESET}"


def status_color(status: TestStatus) -> str:
    """Get color for a test status."""
    return {
        TestStatus.PASS: Colors.GREEN,
        TestStatus.FAIL: Colors.RED,
        TestStatus.WARN: Colors.YELLOW,
        TestStatus.SKIP: Colors.GRAY,
    }.get(status, Colors.RESET)


def status_icon(status: TestStatus) -> str:
    """Get icon for a test status."""
    return {
        TestStatus.PASS: "✓",
        TestStatus.FAIL: "✗",
        TestStatus.WARN: "⚠",
        TestStatus.SKIP: "○",
    }.get(status, "?")


def print_header(text: str) -> None:
    """Print a section header."""
    print()
    print(colorize(f"═══ {text} ═══", Colors.BOLD + Colors.CYAN))


def print_subheader(text: str) -> None:
    """Print a subsection header."""
    print()
    print(colorize(f"─── {text} ───", Colors.BLUE))


def grade_color(grade: str) -> str:
    """Get color for a grade."""
    if grade.startswith("A"):
        return Colors.GREEN
    elif grade.startswith("B"):
        return Colors.CYAN
    elif grade.startswith("C"):
        return Colors.YELLOW
    else:
        return Colors.RED


def main() -> NoReturn:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="DLNA/UPnP Media Server Compliance Tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  dlna-tester 192.168.1.100 8200
  dlna-tester 192.168.1.100 8200 -v
  dlna-tester 192.168.1.100 8200 --timeout 30

This tool tests a DLNA media server for protocol compliance by:
  - Verifying device description and service definitions
  - Testing ContentDirectory service actions (Browse, Search, etc.)
  - Testing ConnectionManager service actions
  - Checking media metadata compliance
  - Verifying resource accessibility
  - Testing protocol compliance (SOAP, HTTP headers, etc.)
""",
    )
    parser.add_argument("host", help="DLNA server IP address or hostname")
    parser.add_argument("port", type=int, help="DLNA server port number")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show verbose output during tests"
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=10.0,
        help="Request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON"
    )
    parser.add_argument(
        "--full-scan",
        action="store_true",
        help="Traverse ALL containers and media items (slower but thorough)",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=1000,
        help="Maximum items to scan in full-scan mode (default: 1000)",
    )
    parser.add_argument(
        "-l",
        "--listing",
        action="store_true",
        help="List the media library tree instead of running tests",
    )
    parser.add_argument(
        "-p",
        "--playmedia",
        action="store_true",
        help="Simulate playing a video file (mkv/mp4) by making HTTP requests like a real DLNA client",
    )

    args = parser.parse_args()

    # --playmedia implies --full-scan
    if args.playmedia:
        args.full_scan = True

    # Disable colors if requested
    if args.no_color:
        Colors.RESET = ""
        Colors.BOLD = ""
        Colors.RED = ""
        Colors.GREEN = ""
        Colors.YELLOW = ""
        Colors.BLUE = ""
        Colors.CYAN = ""
        Colors.GRAY = ""

    if args.listing:
        run_listing(args.host, args.port, args.timeout, args.max_items, args.no_color)
    elif args.playmedia:
        run_playmedia(args.host, args.port, args.timeout, args.max_items, args.verbose)
    elif args.json:
        run_json_output(args.host, args.port, args.timeout, args.verbose, args.full_scan, args.max_items)
    else:
        run_interactive(args.host, args.port, args.timeout, args.verbose, args.full_scan, args.max_items)


def find_video_file(tester: DLNATester, max_items: int) -> MediaItem | None:
    """Find the first video file (mkv/mp4) in the media library."""
    from .tester import MediaItem

    items_scanned = 0

    def search_recursive(object_id: str) -> MediaItem | None:
        nonlocal items_scanned

        if items_scanned >= max_items:
            return None

        result = tester.browse(object_id, "BrowseDirectChildren", "*", 0, 0)
        if result is None:
            return None

        items, _, _ = result

        for item in items:
            if items_scanned >= max_items:
                return None

            items_scanned += 1

            if item.is_container:
                found = search_recursive(item.id)
                if found:
                    return found
            else:
                # Check if it's a video file (mkv or mp4)
                if item.resources:
                    for res in item.resources:
                        url = res.get("url", "").lower()
                        protocol_info = res.get("protocol_info", "").lower()
                        if any(ext in url for ext in [".mkv", ".mp4"]) or \
                           any(fmt in protocol_info for fmt in ["video/x-matroska", "video/mp4"]):
                            return item
        return None

    return search_recursive("0")


def run_playmedia(host: str, port: int, timeout: float, max_items: int, verbose: bool) -> NoReturn:
    """Simulate playing a video file like a real DLNA client would."""
    from .tester import MediaItem

    print_header("DLNA Media Playback Simulation")
    print(f"Server: {colorize(f'{host}:{port}', Colors.BOLD)}")
    print()

    try:
        with DLNATester(host, port, timeout) as tester:
            # Get device info
            device = tester.fetch_device_description()
            if device:
                print(f"Device: {colorize(device.friendly_name, Colors.CYAN)}")

            if tester._content_directory is None:
                print(colorize("Error: ContentDirectory service not available", Colors.RED))
                sys.exit(1)

            print("Scanning for video files (mkv/mp4)...")
            video = find_video_file(tester, max_items)

            if video is None:
                print(colorize("Warning: No mkv/mp4 video files found in media library", Colors.YELLOW))
                sys.exit(0)

            print(f"Found video: {colorize(video.title, Colors.GREEN)}")
            print()

            if not video.resources:
                print(colorize("Error: Video has no playable resources", Colors.RED))
                sys.exit(1)

            # Use the first resource
            resource = video.resources[0]
            url = resource.get("url", "")
            if not url:
                print(colorize("Error: Video resource has no URL", Colors.RED))
                sys.exit(1)

            print_subheader("Simulating DLNA Playback")
            print(f"Resource URL: {colorize(url, Colors.GRAY)}")
            if resource.get("protocol_info"):
                print(f"Protocol Info: {colorize(resource['protocol_info'], Colors.GRAY)}")
            print()

            # Perform the playback simulation
            simulate_playback(tester, url, verbose)

            print()
            print(colorize("✓ Playback simulation completed successfully", Colors.GREEN))
            sys.exit(0)

    except KeyboardInterrupt:
        print()
        print(colorize("Interrupted.", Colors.YELLOW))
        sys.exit(130)
    except Exception as e:
        print(colorize(f"Error: {e}", Colors.RED))
        sys.exit(2)


def simulate_playback(tester: DLNATester, url: str, verbose: bool) -> None:
    """Simulate the HTTP requests a real DLNA client would make to play a video.

    A real DLNA client typically:
    1. Sends a HEAD request to get content info
    2. Sends a GET request with Range header for initial playback
    3. May send additional range requests for seeking
    """
    import time

    full_url = tester._make_url(url)

    # Step 1: HEAD request (get content info)
    print(f"  {colorize('[1/4]', Colors.CYAN)} HEAD request (get content info)...")
    try:
        response = tester.client.head(full_url, follow_redirects=True)
        if verbose:
            print(f"        Status: {response.status_code}")
            print(f"        Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            print(f"        Content-Length: {response.headers.get('Content-Length', 'N/A')}")
            print(f"        Accept-Ranges: {response.headers.get('Accept-Ranges', 'N/A')}")
        content_length = int(response.headers.get('Content-Length', 0))
        if response.status_code == 200:
            print(f"        {colorize('✓ OK', Colors.GREEN)}")
        else:
            print(f"        {colorize(f'⚠ Status {response.status_code}', Colors.YELLOW)}")
    except Exception as e:
        print(f"        {colorize(f'✗ Failed: {e}', Colors.RED)}")
        content_length = 0

    # Step 2: Initial range request (start of file)
    print(f"  {colorize('[2/4]', Colors.CYAN)} GET range request (start of file, bytes=0-65535)...")
    try:
        headers = {
            "Range": "bytes=0-65535",
            "User-Agent": "DLNA-Tester/1.0 UPnP/1.0",
            "transferMode.dlna.org": "Streaming",
        }
        response = tester.client.get(full_url, headers=headers, follow_redirects=True)
        if verbose:
            print(f"        Status: {response.status_code}")
            print(f"        Content-Range: {response.headers.get('Content-Range', 'N/A')}")
            print(f"        Bytes received: {len(response.content)}")
        if response.status_code in (200, 206):
            print(f"        {colorize('✓ OK', Colors.GREEN)}")
        else:
            print(f"        {colorize(f'⚠ Status {response.status_code}', Colors.YELLOW)}")
    except Exception as e:
        print(f"        {colorize(f'✗ Failed: {e}', Colors.RED)}")

    # Step 3: Seek request (middle of file)
    if content_length > 0:
        print(f"  {colorize('[3/4]', Colors.CYAN)} GET range request (seek to middle)...")
        try:
            mid_point = content_length // 2
            end_point = min(mid_point + 65535, content_length - 1)
            headers = {
                "Range": f"bytes={mid_point}-{end_point}",
                "User-Agent": "DLNA-Tester/1.0 UPnP/1.0",
                "transferMode.dlna.org": "Streaming",
            }
            response = tester.client.get(full_url, headers=headers, follow_redirects=True)
            if verbose:
                print(f"        Status: {response.status_code}")
                print(f"        Requested: bytes={mid_point}-{end_point}")
                print(f"        Content-Range: {response.headers.get('Content-Range', 'N/A')}")
                print(f"        Bytes received: {len(response.content)}")
            if response.status_code in (200, 206):
                print(f"        {colorize('✓ OK', Colors.GREEN)}")
            else:
                print(f"        {colorize(f'⚠ Status {response.status_code}', Colors.YELLOW)}")
        except Exception as e:
            print(f"        {colorize(f'✗ Failed: {e}', Colors.RED)}")
    else:
        print(f"  {colorize('[3/4]', Colors.CYAN)} GET range request (seek to middle)...")
        print(f"        {colorize('○ Skipped (unknown content length)', Colors.GRAY)}")

    # Step 4: End of file request (sometimes clients do this)
    if content_length > 65536:
        print(f"  {colorize('[4/4]', Colors.CYAN)} GET range request (end of file)...")
        try:
            start_point = content_length - 65536
            headers = {
                "Range": f"bytes={start_point}-{content_length - 1}",
                "User-Agent": "DLNA-Tester/1.0 UPnP/1.0",
                "transferMode.dlna.org": "Streaming",
            }
            response = tester.client.get(full_url, headers=headers, follow_redirects=True)
            if verbose:
                print(f"        Status: {response.status_code}")
                print(f"        Requested: bytes={start_point}-{content_length - 1}")
                print(f"        Content-Range: {response.headers.get('Content-Range', 'N/A')}")
                print(f"        Bytes received: {len(response.content)}")
            if response.status_code in (200, 206):
                print(f"        {colorize('✓ OK', Colors.GREEN)}")
            else:
                print(f"        {colorize(f'⚠ Status {response.status_code}', Colors.YELLOW)}")
        except Exception as e:
            print(f"        {colorize(f'✗ Failed: {e}', Colors.RED)}")
    else:
        print(f"  {colorize('[4/4]', Colors.CYAN)} GET range request (end of file)...")
        print(f"        {colorize('○ Skipped (file too small or unknown length)', Colors.GRAY)}")


def run_listing(host: str, port: int, timeout: float, max_items: int, no_color: bool) -> NoReturn:
    """List the media library tree."""
    from .tester import MediaItem

    print_header("DLNA Media Library Listing")
    print(f"Server: {colorize(f'{host}:{port}', Colors.BOLD)}")

    try:
        with DLNATester(host, port, timeout) as tester:
            # Get device info
            device = tester.fetch_device_description()
            if device:
                print(f"Device: {colorize(device.friendly_name, Colors.CYAN)}")
            print()

            if tester._content_directory is None:
                print(colorize("Error: ContentDirectory service not available", Colors.RED))
                sys.exit(1)

            # Track counts
            total_containers = 0
            total_items = 0

            def print_item(item: MediaItem, indent: int = 0) -> None:
                """Print a single item with appropriate formatting."""
                prefix = "  " * indent
                if item.is_container:
                    icon = "📁"
                    name = colorize(item.title, Colors.BLUE + Colors.BOLD)
                    count_str = f" ({item.child_count} items)" if item.child_count is not None else ""
                    print(f"{prefix}{icon} {name}{colorize(count_str, Colors.GRAY)}")
                else:
                    # Determine icon based on class
                    if "audioItem" in item.item_class:
                        icon = "🎵"
                    elif "videoItem" in item.item_class:
                        icon = "🎬"
                    elif "imageItem" in item.item_class:
                        icon = "🖼️ "
                    else:
                        icon = "📄"

                    # Get duration if available
                    duration_str = ""
                    if item.resources:
                        dur = item.resources[0].get("duration")
                        if dur:
                            duration_str = colorize(f" [{dur}]", Colors.GRAY)

                    print(f"{prefix}{icon} {item.title}{duration_str}")

            def browse_recursive(object_id: str, indent: int = 0) -> None:
                """Recursively browse and print the tree."""
                nonlocal total_containers, total_items

                if total_containers + total_items >= max_items:
                    return

                result = tester.browse(object_id, "BrowseDirectChildren", "*", 0, 0)
                if result is None:
                    return

                items, num_returned, total_matches = result

                for item in items:
                    if total_containers + total_items >= max_items:
                        print(f"{'  ' * indent}... (max items limit reached)")
                        return

                    print_item(item, indent)

                    if item.is_container:
                        total_containers += 1
                        browse_recursive(item.id, indent + 1)
                    else:
                        total_items += 1

            print(colorize("Media Library:", Colors.BOLD))
            print()
            browse_recursive("0")

            print()
            print(colorize(f"Total: {total_containers} folders, {total_items} files", Colors.CYAN))
            sys.exit(0)

    except KeyboardInterrupt:
        print()
        print(colorize("Interrupted.", Colors.YELLOW))
        sys.exit(130)
    except Exception as e:
        print(colorize(f"Error: {e}", Colors.RED))
        sys.exit(2)


def run_json_output(
    host: str, port: int, timeout: float, verbose: bool, full_scan: bool, max_items: int
) -> NoReturn:
    """Run tests and output results as JSON."""
    import json

    try:
        with DLNATester(host, port, timeout) as tester:
            suite = TestSuite(tester, verbose=verbose, full_scan=full_scan, max_items=max_items)
            suite.run_all_tests()

            summary = suite.get_summary()
            results = [
                {
                    "name": r.name,
                    "category": r.category.value,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                    "weight": r.weight,
                }
                for r in suite.results
            ]

            output = {
                "server": {"host": host, "port": port},
                "summary": summary,
                "results": results,
            }

            if tester.device_info:
                output["device"] = {
                    "friendly_name": tester.device_info.friendly_name,
                    "manufacturer": tester.device_info.manufacturer,
                    "model_name": tester.device_info.model_name,
                    "device_type": tester.device_info.device_type,
                }

            print(json.dumps(output, indent=2))
            sys.exit(0 if summary["failed"] == 0 else 1)

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)


def run_interactive(
    host: str, port: int, timeout: float, verbose: bool, full_scan: bool, max_items: int
) -> NoReturn:
    """Run tests with interactive output."""
    print_header("DLNA/UPnP Media Server Compliance Tester")
    print(f"Target: {colorize(f'{host}:{port}', Colors.BOLD)}")
    print(f"Timeout: {timeout}s")
    if full_scan:
        print(f"Mode: {colorize('Full Scan', Colors.YELLOW)} (max {max_items} items)")

    try:
        with DLNATester(host, port, timeout) as tester:
            suite = TestSuite(tester, verbose=verbose, full_scan=full_scan, max_items=max_items)

            print()
            print("Running compliance tests...")
            if verbose:
                print()

            results = suite.run_all_tests()

            # Print device info if available
            if tester.device_info:
                print_subheader("Device Information")
                info = tester.device_info
                print(f"  Name:         {colorize(info.friendly_name, Colors.BOLD)}")
                print(f"  Manufacturer: {info.manufacturer}")
                print(f"  Model:        {info.model_name}")
                print(f"  Type:         {info.device_type}")
                if info.serial_number:
                    print(f"  Serial:       {info.serial_number}")

            # Group results by category
            by_category: dict[TestCategory, list] = {}
            for r in results:
                if r.category not in by_category:
                    by_category[r.category] = []
                by_category[r.category].append(r)

            # Print results by category
            print_subheader("Test Results")

            for category in TestCategory:
                if category not in by_category:
                    continue

                cat_results = by_category[category]
                passed = sum(1 for r in cat_results if r.status == TestStatus.PASS)
                total = len(cat_results)

                print()
                print(
                    f"  {colorize(category.value, Colors.BOLD)} "
                    f"({passed}/{total} passed)"
                )

                for r in cat_results:
                    icon = status_icon(r.status)
                    color = status_color(r.status)
                    status_str = colorize(f"[{r.status.value}]", color)
                    icon_str = colorize(icon, color)

                    # Truncate long messages
                    msg = r.message
                    if len(msg) > 60:
                        msg = msg[:57] + "..."

                    print(f"    {icon_str} {status_str} {r.name}")
                    if verbose or r.status in (TestStatus.FAIL, TestStatus.WARN):
                        print(f"      {colorize(msg, Colors.GRAY)}")

            # Print summary
            summary = suite.get_summary()
            score, max_score, grade = suite.get_score()
            percentage = (score / max_score * 100) if max_score > 0 else 0

            print_header("Compliance Summary")

            # Stats line
            stats = []
            if summary["passed"]:
                stats.append(colorize(f"{summary['passed']} passed", Colors.GREEN))
            if summary["failed"]:
                stats.append(colorize(f"{summary['failed']} failed", Colors.RED))
            if summary["warned"]:
                stats.append(colorize(f"{summary['warned']} warnings", Colors.YELLOW))
            if summary["skipped"]:
                stats.append(colorize(f"{summary['skipped']} skipped", Colors.GRAY))

            print(f"  Tests: {', '.join(stats)}")
            print(f"  Score: {score:.1f}/{max_score:.1f} ({percentage:.1f}%)")

            # Grade display
            grade_str = colorize(grade, Colors.BOLD + grade_color(grade))
            print()
            print(f"  ╔═══════════════════╗")
            print(f"  ║   GRADE: {grade_str}       ║")
            print(f"  ╚═══════════════════╝")

            # Grade interpretation
            print()
            if grade.startswith("A"):
                print(
                    colorize(
                        "  Excellent! This server has strong DLNA compliance.",
                        Colors.GREEN,
                    )
                )
            elif grade.startswith("B"):
                print(
                    colorize(
                        "  Good compliance with minor issues.",
                        Colors.CYAN,
                    )
                )
            elif grade.startswith("C"):
                print(
                    colorize(
                        "  Acceptable compliance but with notable issues.",
                        Colors.YELLOW,
                    )
                )
            else:
                print(
                    colorize(
                        "  Poor compliance. Major issues detected.",
                        Colors.RED,
                    )
                )

            # Show critical failures
            critical_failures = [
                r for r in results if r.status == TestStatus.FAIL and r.weight >= 1.5
            ]
            if critical_failures:
                print()
                print(colorize("  Critical issues:", Colors.RED + Colors.BOLD))
                for r in critical_failures:
                    print(f"    • {r.name}: {r.message}")

            print()
            sys.exit(0 if summary["failed"] == 0 else 1)

    except KeyboardInterrupt:
        print()
        print(colorize("Interrupted by user.", Colors.YELLOW))
        sys.exit(130)
    except Exception as e:
        print()
        print(colorize(f"Error: {e}", Colors.RED))
        sys.exit(2)


if __name__ == "__main__":
    main()
