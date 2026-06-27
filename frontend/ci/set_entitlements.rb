# Point every build configuration at the Sign in with Apple entitlements file.
# Runs in CI after `npx cap sync ios` (the ios/ folder is generated fresh each
# build, so we can't wire this in Xcode — we edit the generated pbxproj directly).
# Path is relative to the repo root, which is Codemagic's working directory.
require 'xcodeproj'

proj_path = 'frontend/ios/App/App.xcodeproj'
project = Xcodeproj::Project.open(proj_path)
project.targets.each do |target|
  target.build_configurations.each do |config|
    # CODE_SIGN_ENTITLEMENTS is resolved relative to the .xcodeproj's directory
    # (frontend/ios/App), so this points at frontend/ios/App/App/App.entitlements.
    config.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'App/App.entitlements'
  end
end
project.save
puts "Set CODE_SIGN_ENTITLEMENTS for targets: #{project.targets.map(&:name).join(', ')}"
