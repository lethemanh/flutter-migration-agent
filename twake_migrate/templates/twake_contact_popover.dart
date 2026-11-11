// GENERATED FILE - DO NOT EDIT BY HAND.
// Maps @linagora/twake-mui ContactPopover to the approved mobile touch behavior.
import 'package:flutter/material.dart';
import '../tokens/twake_spacing.dart';
import '../tokens/twake_typography.dart';

class TwakeContactPopover extends StatelessWidget {
  final String name;
  final String email;
  final Widget child;
  final List<Widget> actions;
  final bool disabled;
  final VoidCallback? onEmailCopy;
  final VoidCallback? onClose;

  const TwakeContactPopover({
    super.key,
    required this.name,
    required this.email,
    required this.child,
    this.actions = const [],
    this.disabled = false,
    this.onEmailCopy,
    this.onClose,
  });

  Future<void> _open(BuildContext context) async {
    if (disabled) return;
    await showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: TwakeSpacing.p2,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(name, style: TwakeTypography.h6),
            if (email.isNotEmpty) ...[
              const SizedBox(height: TwakeSpacing.xs),
              SelectableText(email, style: TwakeTypography.body2),
            ],
            if (actions.isNotEmpty) ...[
              const SizedBox(height: TwakeSpacing.m),
              Wrap(spacing: TwakeSpacing.xs, runSpacing: TwakeSpacing.xs, children: actions),
            ],
          ],
        ),
      ),
    );
    onClose?.call();
  }

  @override
  Widget build(BuildContext context) => GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: disabled ? null : () => _open(context),
        child: child,
      );
}
