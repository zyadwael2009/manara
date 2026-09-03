import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../theme/app_text_styles.dart';
import 'silent_error.dart';

/// Phase 30 · T4 — generic infinite-scroll list.
///
/// One widget, three responsibilities:
///   1. Fetch page 1 on init via [fetchPage].
///   2. Fetch page N+1 when the user scrolls to within [prefetchExtent]
///      of the bottom.
///   3. Render a compact retry chip when a page fetch fails (uses the
///      existing [SilentError]) without wiping the pages already loaded.
///
/// The list stays [ListView.separated]-shaped so callers get familiar
/// separators + reverse + padding controls. Pull-to-refresh is wired
/// to [refresh()] via a [GlobalKey] the caller can hold.
///
/// Callback contract:
///   Future<PagedResult<T>> fetchPage(int page)
///   Widget itemBuilder(BuildContext context, T item, int index)
///
/// `PagedResult` mirrors the server's envelope:
///   items    — this page's rows
///   hasMore  — false when we've reached the end
class PagedResult<T> {
  final List<T> items;
  final bool hasMore;
  const PagedResult({required this.items, required this.hasMore});
}

class PagedListView<T> extends StatefulWidget {
  final Future<PagedResult<T>> Function(int page) fetchPage;
  final Widget Function(BuildContext, T, int) itemBuilder;
  final Widget? separator;
  final EdgeInsetsGeometry padding;
  final Widget? emptyPlaceholder;
  final int firstPage;
  final double prefetchExtent;

  const PagedListView({
    super.key,
    required this.fetchPage,
    required this.itemBuilder,
    this.separator,
    this.padding = EdgeInsets.zero,
    this.emptyPlaceholder,
    this.firstPage = 1,
    this.prefetchExtent = 240.0,
  });

  @override
  State<PagedListView<T>> createState() => PagedListViewState<T>();
}

class PagedListViewState<T> extends State<PagedListView<T>> {
  final _scroll = ScrollController();
  final List<T> _items = [];
  int _nextPage = 1;
  bool _loading = false;
  bool _hasMore = true;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _nextPage = widget.firstPage;
    _scroll.addListener(_onScroll);
    _loadNext();
  }

  @override
  void dispose() {
    _scroll.removeListener(_onScroll);
    _scroll.dispose();
    super.dispose();
  }

  /// Public for a parent RefreshIndicator: reset + reload from page 1.
  Future<void> refresh() async {
    if (!mounted) return;
    setState(() {
      _items.clear();
      _nextPage = widget.firstPage;
      _hasMore = true;
      _error = null;
    });
    await _loadNext();
  }

  void _onScroll() {
    if (_loading || !_hasMore || _error != null) return;
    if (_scroll.position.pixels >=
        _scroll.position.maxScrollExtent - widget.prefetchExtent) {
      _loadNext();
    }
  }

  Future<void> _loadNext() async {
    if (_loading || !_hasMore) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await widget.fetchPage(_nextPage);
      if (!mounted) return;
      setState(() {
        _items.addAll(page.items);
        _hasMore = page.hasMore;
        _nextPage += 1;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_items.isEmpty && _loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_items.isEmpty && _error != null) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: SilentError(onRetry: _loadNext),
      );
    }
    if (_items.isEmpty && widget.emptyPlaceholder != null) {
      return widget.emptyPlaceholder!;
    }
    // Extra "loading spinner OR retry chip OR nothing" cell at the end.
    final trailingCount = (_hasMore || _error != null) ? 1 : 0;
    final total = _items.length + trailingCount;
    return ListView.separated(
      controller: _scroll,
      padding: widget.padding,
      itemCount: total,
      separatorBuilder: (_, __) =>
          widget.separator ?? const SizedBox(height: 0),
      itemBuilder: (context, i) {
        if (i >= _items.length) {
          if (_error != null) {
            return Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: SilentError(
                onRetry: _loadNext,
                label: 'Load more failed — tap to retry',
              ),
            );
          }
          return const Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: Center(
              child: SizedBox(
                width: 20, height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          );
        }
        return widget.itemBuilder(context, _items[i], i);
      },
    );
  }
}

/// Small helper for screens that don't want a full PagedListView shell
/// — e.g. an admin table that just wants "Next page" / "Prev page"
/// buttons. Renders a compact 3-item row.
class PagedFooter extends StatelessWidget {
  final int page;
  final bool hasMore;
  final VoidCallback? onPrev;
  final VoidCallback? onNext;
  const PagedFooter({
    super.key,
    required this.page,
    required this.hasMore,
    this.onPrev,
    this.onNext,
  });
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          OutlinedButton.icon(
            onPressed: page > 1 ? onPrev : null,
            icon: const Icon(Icons.chevron_left_rounded, size: 18),
            label: const Text('Prev'),
          ),
          const SizedBox(width: AppSpacing.md),
          Text('Page $page',
              style: AppTextStyles.caption(context,
                  color: AppColors.textMuted)),
          const SizedBox(width: AppSpacing.md),
          OutlinedButton.icon(
            onPressed: hasMore ? onNext : null,
            icon: const Icon(Icons.chevron_right_rounded, size: 18),
            label: const Text('Next'),
          ),
        ],
      ),
    );
  }
}
