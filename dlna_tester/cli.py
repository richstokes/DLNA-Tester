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

    args = parser.parse_args()

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

    if args.json:
        run_json_output(args.host, args.port, args.timeout, args.verbose)
    else:
        run_interactive(args.host, args.port, args.timeout, args.verbose)


def run_json_output(host: str, port: int, timeout: float, verbose: bool) -> NoReturn:
    """Run tests and output results as JSON."""
    import json

    try:
        with DLNATester(host, port, timeout) as tester:
            suite = TestSuite(tester, verbose=verbose)
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


def run_interactive(host: str, port: int, timeout: float, verbose: bool) -> NoReturn:
    """Run tests with interactive output."""
    print_header("DLNA/UPnP Media Server Compliance Tester")
    print(f"Target: {colorize(f'{host}:{port}', Colors.BOLD)}")
    print(f"Timeout: {timeout}s")

    try:
        with DLNATester(host, port, timeout) as tester:
            suite = TestSuite(tester, verbose=verbose)

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
