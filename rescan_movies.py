#!/usr/bin/env python3
import utils

if __name__ == "__main__":
    print("[INFO] Starting movie rescan...")
    utils.scan_movies()
    print("[INFO] Rescan completed. New movies added to DB.")
