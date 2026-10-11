import unittest

from video_downloader.domain.models import DownloadProgress, ProgressState
from video_downloader.presentation.progress_view import ProgressPresenter


class ProgressViewTests(unittest.TestCase):
    def test_exact_total_is_stable_and_estimate_is_not_used(self):
        presenter = ProgressPresenter()
        first = presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 100, 1000, 100), 0)
        second = presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 200, None, 200), 1)
        self.assertIn("of 1000 B", first.details)
        self.assertIn("of 1000 B", second.details)
        self.assertEqual(second.fraction, 0.2)
        self.assertIn("200 B/s", second.details)
        self.assertIn("00:08 remaining", second.details)

    def test_unknown_total_stays_honest(self):
        view = ProgressPresenter().update(
            DownloadProgress(ProgressState.DOWNLOADING, 50, None, 10, 500), 0)
        self.assertIsNone(view.fraction)
        self.assertIn("total unknown", view.details)
        self.assertIn("≈08:20 remaining", view.details)
        self.assertNotIn("500", view.details)

    def test_estimated_eta_ignores_short_lived_spike(self):
        presenter = ProgressPresenter()
        presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 50, None, 10, 600), 0)
        view = presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 60, None, 20, 1200), 1)
        self.assertIn("≈", view.details)
        self.assertNotIn("20:00 remaining", view.details)
        self.assertIn("20 B/s", view.details)

    def test_counter_reset_or_overrun_invalidates_total(self):
        presenter = ProgressPresenter()
        presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 90, 100, 10), 0)
        view = presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 110, 100, 10), 1)
        self.assertIsNone(view.fraction)
        self.assertIn("total unknown", view.details)

    def test_conflicting_exact_totals_become_unknown(self):
        presenter = ProgressPresenter()
        presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 10, 100, 10), 0)
        view = presenter.update(DownloadProgress(ProgressState.DOWNLOADING, 20, 120, 10), 1)
        self.assertIsNone(view.fraction)
        self.assertIn("total unknown", view.details)


if __name__ == "__main__":
    unittest.main()
