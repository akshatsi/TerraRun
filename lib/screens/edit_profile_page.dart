import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import '../services/social_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

/// Change your name and bio. Pops with `true` once the server has saved.
class EditProfilePage extends StatefulWidget {
  final String name;
  final String bio;

  const EditProfilePage({super.key, required this.name, this.bio = ''});

  @override
  State<EditProfilePage> createState() => _EditProfilePageState();
}

class _EditProfilePageState extends State<EditProfilePage> {
  static const _bioLimit = 160;

  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name = TextEditingController(
    text: widget.name,
  );
  late final TextEditingController _bio = TextEditingController(
    text: widget.bio,
  );

  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _bio.dispose();
    super.dispose();
  }

  String? _validateName(String? value) {
    final length = (value ?? '').trim().length;
    if (length < 2 || length > 40) return 'Use 2 to 40 characters';
    return null;
  }

  Future<void> _save() async {
    if (_saving || !_formKey.currentState!.validate()) return;

    setState(() {
      _saving = true;
      _error = null;
    });

    final result = await SocialService.updateProfile(_name.text, _bio.text);
    if (!mounted) return;

    if (result['success'] == true) {
      Navigator.of(context).pop(true);
    } else {
      setState(() {
        _saving = false;
        _error = result['message']?.toString() ?? 'Could not save profile';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Column(
          children: [
            ScreenHeader(
              title: 'Edit profile',
              leading: AppIconButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.of(context).pop(),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      AppTextField(
                        controller: _name,
                        label: 'Name',
                        hint: 'Your name',
                        validator: _validateName,
                      ),
                      const SizedBox(height: 20),
                      ShadInputFormField(
                        controller: _bio,
                        label: const Text('Bio'),
                        placeholder: const Text('Tell runners about yourself'),
                        maxLines: 4,
                        minLines: 3,
                        maxLength: _bioLimit,
                        keyboardType: TextInputType.multiline,
                        description: ValueListenableBuilder(
                          valueListenable: _bio,
                          builder: (context, value, _) => Align(
                            alignment: Alignment.centerRight,
                            child: Text('${value.text.length}/$_bioLimit'),
                          ),
                        ),
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 12),
                        ErrorBanner(_error!),
                      ],
                      const SizedBox(height: 20),
                      PrimaryButton(
                        label: 'Save',
                        loading: _saving,
                        onPressed: _saving ? null : _save,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
