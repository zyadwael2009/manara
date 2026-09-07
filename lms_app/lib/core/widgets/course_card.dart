import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../models/course.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../theme/app_text_styles.dart';

/// The catalog / instructor-home card. Hero-tagged by course id so tapping
/// through to detail flies the thumbnail smoothly.
class CourseCard extends StatefulWidget {
  final Course course;
  final VoidCallback onTap;
  final bool showStatusBadge;

  const CourseCard({
    super.key,
    required this.course,
    required this.onTap,
    this.showStatusBadge = false,
  });

  @override
  State<CourseCard> createState() => _CourseCardState();
}

class _CourseCardState extends State<CourseCard> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) => setState(() => _pressed = false),
      onTapCancel: () => setState(() => _pressed = false),
      onTap: widget.onTap,
      child: AnimatedScale(
        scale: _pressed ? 0.98 : 1.0,
        duration: const Duration(milliseconds: 150),
        curve: Curves.easeOut,
        child: Card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Thumbnail(course: widget.course),
              Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            widget.course.title,
                            style: AppTextStyles.h3(context),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (widget.showStatusBadge) ...[
                          const SizedBox(width: AppSpacing.sm),
                          _StatusPill(status: widget.course.status),
                        ],
                      ],
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    if ((widget.course.instructorName ?? '').isNotEmpty)
                      Text(
                        'by ${widget.course.instructorName}',
                        style: AppTextStyles.caption(
                          context,
                          color: isDark ? AppColors.textMutedDark : AppColors.textMuted,
                        ),
                      ),
                    const SizedBox(height: AppSpacing.md),
                    Row(
                      children: [
                        _CategoryChip(label: widget.course.category),
                        const Spacer(),
                        Text(
                          widget.course.isFree ? 'Free' : '\$${widget.course.price.toStringAsFixed(2)}',
                          style: AppTextStyles.bodyStrong(
                            context,
                            color: widget.course.isFree ? AppColors.success : AppColors.primary,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  final Course course;
  const _Thumbnail({required this.course});

  @override
  Widget build(BuildContext context) {
    final url = course.thumbnailUrl;
    return Hero(
      tag: 'course-hero-${course.id}',
      child: AspectRatio(
        aspectRatio: 16 / 9,
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                AppColors.primary.withValues(alpha: 0.85),
                AppColors.primaryDark.withValues(alpha: 0.9),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: (url != null && url.isNotEmpty)
              ? CachedNetworkImage(
                  imageUrl: url,
                  fit: BoxFit.cover,
                  fadeInDuration: const Duration(milliseconds: 300),
                  errorWidget: (_, _, _) => const _PlaceholderGlyph(),
                )
              : const _PlaceholderGlyph(),
        ),
      ),
    );
  }
}

class _PlaceholderGlyph extends StatelessWidget {
  const _PlaceholderGlyph();
  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Icon(Icons.menu_book_rounded, color: Colors.white70, size: 44),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  final String label;
  const _CategoryChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.primarySoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        label,
        style: AppTextStyles.micro(context, color: AppColors.primary),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    final published = status == 'published';
    final bg = published ? AppColors.successSoft : AppColors.warningSoft;
    final fg = published ? AppColors.success : AppColors.warning;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        published ? 'Published' : 'Draft',
        style: AppTextStyles.micro(context, color: fg),
      ),
    );
  }
}
